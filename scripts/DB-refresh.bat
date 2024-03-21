
docker stop spacetraders_db_container
docker rm spacetraders_db_container
docker pull ctriatanitan/spacetraders_db:latest


docker network create spacetraders

docker run -d --env-file scripts\.env -p 5432:5432 --network spacetraders --name spacetraders_db_container ctriatanitan/spacetraders_db:latest
