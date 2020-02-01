from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


class EmailClient:

    def __init__(self, email_api_key, email_from, email_to):
        self.__client = SendGridAPIClient(email_api_key)
        self.__email_from = email_from
        self.__email_to = email_to

    def get_email_to(self):
        return self.__email_to

    def send_message(self, subject, body, email_to):
        message = Mail(
            from_email=self.__email_from,
            to_emails=email_to or self.__email_to,
            subject=subject,
            html_content=body
        )
        return self.__client.send(message)
