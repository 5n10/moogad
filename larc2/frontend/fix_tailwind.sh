#!/bin/bash

# Install required dependencies
npm install -D tailwindcss@latest postcss@latest autoprefixer@latest

# Initialize Tailwind CSS configuration
npx tailwindcss init -p

# Create CSS directory if it doesn't exist
mkdir -p src/styles

# Initial build of Tailwind CSS
npx tailwindcss -i ./src/index.css -o ./src/styles/tailwind.css

# Make the script executable
chmod +x fix_tailwind.sh

echo "Tailwind CSS setup completed successfully!"
