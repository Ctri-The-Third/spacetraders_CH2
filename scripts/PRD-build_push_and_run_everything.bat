docker buildx build  -f scripts\.dockerfile -t ctriatanitan/spacetraders_ch2_ui --platform linux/amd64,linux/arm64  --push .

docker compose  -f "scripts\all_in_one_compose.yml" up