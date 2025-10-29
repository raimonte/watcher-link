APP=app.main:app
HOST=127.0.0.1
PORT=8888

run-api:
	uvicorn $(APP) --reload --host $(HOST) --port $(PORT)

migrate:
	yoyo apply --database $(POSTGRES_URL) ./app/migrations
