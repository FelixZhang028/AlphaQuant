<script setup>
defineProps({
  label: { type: String, default: '' },
  type: { type: String, default: 'text' }, // text | number | date | select | textarea | checkbox
  modelValue: { type: [String, Number, Boolean], default: '' },
  options: { type: Array, default: () => [] }, // [{ value, label }]
  placeholder: { type: String, default: '' },
  min: { type: Number, default: null },
  max: { type: Number, default: null },
  step: { type: [Number, String], default: null },
  disabled: { type: Boolean, default: false },
  hint: { type: String, default: '' },
  rows: { type: Number, default: 3 },
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <label class="block">
    <span class="mb-1 block text-xs text-slate-400">{{ label }}</span>
    <select
      v-if="type === 'select'"
      :value="modelValue"
      :disabled="disabled"
      class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 disabled:opacity-50"
      @change="emit('update:modelValue', $event.target.value)"
    >
      <option v-for="o in options" :key="o.value" :value="o.value" class="bg-ink">{{ o.label }}</option>
    </select>
    <p v-if="type === 'select' && hint" class="mt-1 text-xs text-slate-500">{{ hint }}</p>
    <textarea
      v-else-if="type === 'textarea'"
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      :disabled="disabled"
      class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 disabled:opacity-50"
      @input="emit('update:modelValue', $event.target.value)"
    />
    <div v-else-if="type === 'checkbox'" class="flex items-center gap-2.5 pt-1">
      <input
        type="checkbox"
        :checked="modelValue"
        :disabled="disabled"
        class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
        @change="emit('update:modelValue', $event.target.checked)"
      />
      <span class="text-sm text-slate-300">{{ hint || label }}</span>
    </div>
    <input
      v-else
      :type="type === 'number' ? 'number' : type"
      :value="modelValue"
      :placeholder="placeholder"
      :min="min"
      :max="max"
      :step="step"
      :disabled="disabled"
      class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 disabled:opacity-50"
      @input="emit('update:modelValue', $event.target.value)"
    />
  </label>
</template>
