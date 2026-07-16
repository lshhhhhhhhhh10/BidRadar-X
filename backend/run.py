import uvicorn


if __name__ == "__main__":
    # A stable demo server is more important than file watching here.  Uvicorn's
    # reloader used to terminate the parent process whenever backend files
    # changed, which also brought down the local product flow.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
