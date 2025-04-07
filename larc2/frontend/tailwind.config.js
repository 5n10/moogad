/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html",
  ],
  theme: {
    extend: {
      colors: {
        'base-bg': '#18181b',
        'base-surface': '#242424',
        'base-panel': '#242424',
        'base-border': '#3f3f46',
        'base-border-light': '#52525b',
        'base-content': '#fafafa',
        'base-content-medium': '#a1a1aa',
        'base-content-subtle': '#71717a',
        'base-surface-alt': '#36363b',
        'accent': '#7dd3fc',
        'accent-dim': '#22d3ee',
        'success': '#84cc16',
        'error': '#ef4444',
        'mod-src': '#a78bfa',
      },
      boxShadow: {
        'module': '0px 2px 6px rgba(0, 0, 0, 0.25)',
      }
    },
  },
  plugins: [],
}
