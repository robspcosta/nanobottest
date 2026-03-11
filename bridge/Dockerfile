FROM node:20-slim

WORKDIR /app

COPY package*.json tsconfig.json ./
RUN npm install

COPY src/ ./src/
RUN npm run build

# Default port
EXPOSE 3001

CMD ["node", "dist/index.js"]
