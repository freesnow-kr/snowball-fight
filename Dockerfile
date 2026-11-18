# Render 등 Docker 로 배포. 서버는 PORT 환경변수(없으면 8000)에서 연다.
FROM denoland/deno:2.5.6
WORKDIR /app
COPY . .
RUN deno cache server.ts
USER deno
CMD ["deno", "run", "--allow-net", "--allow-read", "--allow-env", "server.ts"]
