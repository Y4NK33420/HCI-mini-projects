/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#4CAF50',
        secondary: '#2196F3',
        accent: '#FFC107',
        dark: '#212121',
        light: '#F5F5F5',
      },
    },
  },
  plugins: [],
}

