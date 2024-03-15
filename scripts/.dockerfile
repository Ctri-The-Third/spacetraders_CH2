FROM python:3-slim-bookworm
Copy ./spacetraders_sdk/requirements.txt ./sdk_requirements.txt
run python -m pip install -r sdk_requirements.txt
copy ./requirements.txt ./requirements.txt
run python -m pip install -r requirements.txt

copy ./spacetraders_sdk  ./spacetraders_sdk
workdir spacetraders_sdk
run python3 -m build
run python3 -m pip install dist/straders-2.2.0-py3-none-any.whl --force-reinstall


workdir ..
copy *.py ./
copy ./classes ./classes
copy ./static ./static
copy ./templates ./templates

EXPOSE 3000
ENV ST_DB_USER=spacetraders 

#cmd ["python", "main.py"]
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "main:app", "--bind", "0.0.0.0:3000"]

# gunicorn --worker-class eventlet -w 1 main:app --bind 0.0.0.0:3000