docker login
docker buildx build --push --platform linux/amd64,linux/arm64  -t ctriatanitan/spacetraders_ch2_ui:latest -f scripts/.dockerfile .



docker stop spacetraders_ch2_ui_container
docker rm spacetraders_ch2_ui_container
docker pull ctriatanitan/spacetraders_ch2_ui:latest
docker network create spacetraders

docker run -d --env-file scripts\.env -p 3000:3000 --network spacetraders --name spacetraders_ch2_ui_container ctriatanitan/spacetraders_ch2_ui:latest
