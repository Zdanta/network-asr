import unittest

from app.core.exceptions import AppException
from app.core.security import create_download_ticket, parse_download_ticket


class DownloadTicketTest(unittest.TestCase):
    def test_ticket_is_bound_to_user_and_task(self) -> None:
        ticket, expires_at = create_download_ticket(123, "TASK001")

        self.assertGreater(expires_at, 0)
        self.assertEqual(parse_download_ticket(ticket), (123, "TASK001"))

    def test_tampered_ticket_is_rejected(self) -> None:
        ticket, _ = create_download_ticket(123, "TASK001")
        payload, signature = ticket.split(".", 1)
        tampered = f"{payload}A.{signature}"

        with self.assertRaises(AppException):
            parse_download_ticket(tampered)


if __name__ == "__main__":
    unittest.main()
