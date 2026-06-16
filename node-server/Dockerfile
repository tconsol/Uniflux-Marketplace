FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev

COPY src/ ./src/
COPY .env ./

EXPOSE 3085

CMD ["node", "src/app.js"]
