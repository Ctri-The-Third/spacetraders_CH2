docker stop spacetraders_db
docker rm spacetraders_db
docker pull ctriatanitan/spacetraders_db:latest
docker run -d --env-file scripts\.env -p 6432:5432 --name spacetraders_db ctriatanitan/spacetraders_db:latest
