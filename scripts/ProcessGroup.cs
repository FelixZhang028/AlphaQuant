// Kill-on-close Windows job: all descendants stop even if a parent already exited.
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace FellowQuant.Launcher
{
    public sealed class ProcessGroup : IDisposable
    {
        private IntPtr job;
        [StructLayout(LayoutKind.Sequential)]
        private struct BasicLimits
        {
            public long ProcessTime, JobTime;
            public uint Flags;
            public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
            public uint ActiveProcesses;
            public UIntPtr Affinity;
            public uint Priority, Scheduling;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
        [StructLayout(LayoutKind.Sequential)]
        private struct ExtendedLimits
        {
            public BasicLimits Basic;
            public IoCounters Io;
            public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
        }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct StartupInfo
        {
            public int Size;
            public string Reserved, Desktop, Title;
            public uint X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
            public short ShowWindow, ReservedSize;
            public IntPtr ReservedBytes, Input, Output, Error;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct ProcessInfo { public IntPtr Process, Thread; public uint ProcessId, ThreadId; }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(IntPtr handle, int infoClass, ref ExtendedLimits info, uint size);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr handle, IntPtr process);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateJobObject(IntPtr handle, uint code);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetHandleInformation(IntPtr handle, uint mask, uint flags);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateFile(string name, uint access, uint share, IntPtr attributes,
            uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CreateProcess(string application, StringBuilder command, IntPtr processAttributes,
            IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment, string directory,
            ref StartupInfo startup, out ProcessInfo info);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateProcess(IntPtr process, uint code);

        public ProcessGroup()
        {
            job = CreateJobObject(IntPtr.Zero, null); // Not inheritable by child processes.
            if (job == IntPtr.Zero) throw new Win32Exception();
            var limits = new ExtendedLimits();
            limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(typeof(ExtendedLimits))))
            {
                int error = Marshal.GetLastWin32Error();
                Dispose();
                throw new Win32Exception(error);
            }
        }

        // Windows CRT argv quoting, including embedded quotes and trailing slashes.
        private static string Quote(string value)
        {
            if (value.Length > 0 && value.IndexOfAny(new char[] { ' ', '\t', '\n', '\r', '"' }) < 0) return value;
            var result = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { slashes++; continue; }
                result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
                result.Append(c);
                slashes = 0;
            }
            result.Append('\\', slashes * 2).Append('"');
            return result.ToString();
        }

        public Process Start(string executable, string[] arguments, string directory, string stdout, string stderr)
        {
            if (job == IntPtr.Zero) throw new ObjectDisposedException("ProcessGroup");
            var command = new StringBuilder(Quote(executable));
            foreach (string argument in arguments) command.Append(' ').Append(Quote(argument));
            using (var output = new FileStream(stdout, FileMode.Create, FileAccess.Write, FileShare.ReadWrite))
            using (var error = new FileStream(stderr, FileMode.Create, FileAccess.Write, FileShare.ReadWrite))
            using (var input = new Microsoft.Win32.SafeHandles.SafeFileHandle(
                CreateFile("NUL", 0x80000000, 3, IntPtr.Zero, 3, 0x80, IntPtr.Zero), true))
            {
                if (input.IsInvalid) throw new Win32Exception();
                var startup = new StartupInfo();
                startup.Size = Marshal.SizeOf(typeof(StartupInfo));
                startup.Flags = 0x100; // STARTF_USESTDHANDLES
                startup.Input = input.DangerousGetHandle();
                startup.Output = output.SafeFileHandle.DangerousGetHandle();
                startup.Error = error.SafeFileHandle.DangerousGetHandle();
                foreach (IntPtr handle in new IntPtr[] { startup.Input, startup.Output, startup.Error })
                    if (!SetHandleInformation(handle, 1, 1)) throw new Win32Exception();
                ProcessInfo info;
                // Suspended creation prevents spawning a child before joining the job.
                if (!CreateProcess(executable, command, IntPtr.Zero, IntPtr.Zero, true,
                    0x08000004, IntPtr.Zero, directory, ref startup, out info)) throw new Win32Exception();
                try
                {
                    if (!AssignProcessToJobObject(job, info.Process)) throw new Win32Exception();
                    var process = Process.GetProcessById((int)info.ProcessId);
                    if (ResumeThread(info.Thread) == uint.MaxValue) throw new Win32Exception();
                    return process;
                }
                catch { TerminateProcess(info.Process, 1); throw; }
                finally { CloseHandle(info.Thread); CloseHandle(info.Process); }
            }
        }

        public void Stop()
        {
            if (job == IntPtr.Zero) return;
            try { if (!TerminateJobObject(job, 0)) throw new Win32Exception(); }
            finally { Dispose(); }
        }
        public void Dispose()
        {
            if (job == IntPtr.Zero) return;
            IntPtr handle = job;
            job = IntPtr.Zero;
            CloseHandle(handle);
        }
    }
}
