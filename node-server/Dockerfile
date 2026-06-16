FROM node:20-alpine AS base
WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --omit=dev

# Copy source
COPY . .

# Remove example env so it doesn't shadow real one
RUN rm -f .env.example

EXPOSE 8080

ENV NODE_ENV=production

CMD ["node", "src/app.js"]
