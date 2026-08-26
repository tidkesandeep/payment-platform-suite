"""Locust user that POSTs /v1/payments. 200 is success even when policy declines."""

from __future__ import annotations

from locust import HttpUser, constant, task

from loadtest.payload import human_payment, payment_headers


class AuthorizeUser(HttpUser):
    wait_time = constant(0)

    @task
    def post_payment(self) -> None:
        with self.client.post(
            "/v1/payments",
            headers=payment_headers(),
            json=human_payment(),
            name="POST /v1/payments",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")
