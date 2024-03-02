docker build  -f scripts\.dockerfile -t ctriatanitan/spacetraders_ch2_ui  .
docker stop spacetraders_ch2_ui
docker rm spacetraders_ch2_ui
docker run -d -p 3000:3000 --name spacetraders_ch2_ui --env-file scripts/.env ctriatanitan/spacetraders_ch2_ui 
