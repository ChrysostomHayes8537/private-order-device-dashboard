import uvicorn


def main() -> None:
    uvicorn.run(
        "order_dashboard.order_status_service:app_from_environment",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
