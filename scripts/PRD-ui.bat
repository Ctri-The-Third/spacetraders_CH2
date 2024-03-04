docker login
docker buildx build --push --platform linux/amd64,linux/arm64  -t ctriatanitan/spacetraders_ch2_ui:latest -f scripts/.dockerfile .



docker stop spacetraders_ch2_ui
docker rm spacetraders_ch2_ui
docker pull ctriatanitan/spacetraders_ch2_ui:latest
docker run -d --env-file scripts\.env -p 3000:3000 --name spacetraders_ch2_ui ctriatanitan/spacetraders_ch2_ui:latest
