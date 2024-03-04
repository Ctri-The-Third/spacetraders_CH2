FROM python:3-slim-bookworm
Copy ./spacetraders_sdk ./spacetraders_sdk 
run python -m pip install -r spacetraders_sdk/requirements.txt

workdir spacetraders_sdk
run python3 -m build
run python3 -m pip install dist/straders-2.1.5-py3-none-any.whl --force-reinstall

copy ./requirements.txt ./requirements.txt
run python -m pip install -r requirements.txt

workdir ..
copy *.py ./
copy ./static ./static
copy ./templates ./templates

EXPOSE 3000
ENV ST_DB_USER=spacetraders 

cmd ["python", "main.py"]
# CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "main:app", "--bind", "0.0.0.0:3000"]
