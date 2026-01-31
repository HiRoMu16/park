# ============================================
# マルチステージビルド: Next.jsフロントエンド
# ============================================

# ステージ1: 依存関係のインストール
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# パッケージファイルをコピーして依存関係をインストール
COPY package.json package-lock.json* ./
RUN \
  if [ -f package-lock.json ]; then npm ci; \
  else npm install; \
  fi

# ステージ2: アプリケーションのビルド
FROM node:20-alpine AS builder
WORKDIR /app

# 依存関係をコピー
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next.jsのテレメトリを無効化
ENV NEXT_TELEMETRY_DISABLED 1

# プロダクションビルドを実行
RUN npm run build

# ステージ3: プロダクション実行環境
FROM node:20-alpine AS runner
WORKDIR /app

# プロダクション環境変数の設定
ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

# セキュリティ: 非rootユーザーで実行
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# ビルド成果物をコピー
COPY --from=builder /app/public ./public

# Next.jsのスタンドアロン出力を利用
# next.config.jsにoutput: 'standalone'を追加する場合に有効
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# 非rootユーザーに切り替え
USER nextjs

# ポート3000を公開
EXPOSE 3000
ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

# アプリケーションを起動
CMD ["node", "server.js"]
