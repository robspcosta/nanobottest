FROM node:20-slim

WORKDIR /app

COPY package.json ./
# Copy lockfile only if it exists
COPY package-lock.json* ./
COPY tsconfig.json* ./

RUN npm install --no-audit && npm cache clean --force

COPY src/ ./src/
RUN npm run build

# Default port
EXPOSE 3001

CMD ["node", "dist/index.js"]
