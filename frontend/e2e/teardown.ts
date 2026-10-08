export default async function teardown() {
  // Let the owned Python server exit cleanly before Playwright's Windows cleanup.
  await fetch("http://127.0.0.1:8001/__test_shutdown", {
    method: "POST",
  }).catch(() => {});
  for (let i = 0; i < 50; i++) {
    try {
      await fetch("http://127.0.0.1:8001/api/v1/health");
    } catch {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}
