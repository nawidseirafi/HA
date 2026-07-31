import type { Config } from 'tailwindcss';

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        graphite: '#030303',
        tealsteel: '#f59e0b',
      },
      borderRadius: {
        ui: '8px',
      },
    },
  },
  plugins: [],
} satisfies Config;
