/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        brand: '#2563eb',
        'brand-dark': '#38bdf8',
      },
    },
  },
  plugins: [],
}

