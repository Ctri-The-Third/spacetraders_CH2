
docker login 
docker buildx build --push --platform linux/amd64,linux/arm64  -t ctriatanitan/spacetraders_db:latest -f spacetraders_sdk/postgres.dockerfile spacetraders_sdk/.



docker stop spacetraders_db_container
docker rm spacetraders_db_container
docker pull ctriatanitan/spacetraders_db:latest


docker network create spacetraders

docker run -d --env-file scripts\.env -p 5432:5432 --network spacetraders --name spacetraders_db_container ctriatanitan/spacetraders_db:latest
