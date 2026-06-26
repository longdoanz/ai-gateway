FROM node:20-alpine AS builder
WORKDIR /app
ARG API_URL=http://localhost:8000
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ARG NEXT_BASE_PATH=/webui
ARG NEXT_PUBLIC_NINE_ROUTER_ENABLED=true
ARG NEXT_PUBLIC_NINE_ROUTER_URL
ENV API_URL=$API_URL
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID
ENV NEXT_BASE_PATH=$NEXT_BASE_PATH
ENV NEXT_PUBLIC_NINE_ROUTER_ENABLED=$NEXT_PUBLIC_NINE_ROUTER_ENABLED
ENV NEXT_PUBLIC_NINE_ROUTER_URL=$NEXT_PUBLIC_NINE_ROUTER_URL
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
