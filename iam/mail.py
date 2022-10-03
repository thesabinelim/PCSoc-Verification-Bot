"""Handle email functions."""

import boto3
from botocore.exceptions import ClientError
from discord.ext.commands import Cog
from re import search

from iam.log import new_logger
from iam.config import EMAIL, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

LOG = new_logger(__name__)
"""Logger for this module."""

COG_NAME = "Mail"
"""Name of this module's cog."""

EMAIL_REGEX = r"^([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)$"
"""Any string that matches this regex is a valid email."""


def setup(bot):
    """Add Mail cog to bot and set up logging.

    Args:
        bot: Bot object to add cog to.
    """
    LOG.debug(f"Setting up {__name__} extension...")
    cog = Mail(LOG)
    LOG.debug(f"Initialised {COG_NAME} cog")
    bot.add_cog(cog)
    LOG.debug(f"Added {COG_NAME} cog to bot")


def teardown(bot):
    LOG.debug(f"Tearing down {__name__} extension")
    """Remove Mail cog from bot and remove logging."""
    bot.remove_cog(COG_NAME)
    LOG.debug(f"Removed {COG_NAME} cog from bot")
    for handler in LOG.handlers:
        LOG.removeHandler(handler)


class MailError(Exception):
    """Email failed to send.
    
    Attributes:
        recipient: String representing recipient email address.
    """

    def __init__(self, recipient):
        """Init exception with given message.

        Args:
            recipient: String representing recipient email address.
        """
        self.recipient = recipient

    def notify(self):
        """Default handler for this exception.

        Log msg as error.
        """
        LOG.error(f"Email for recipient '{self.recipient}' failed to send")


def is_valid_email(email):
    """Returns whether given string is a valid email.

    Args:
        email: String to validate.

    Returns:
        Boolean value representing whether string is a valid email.
    """
    return search(EMAIL_REGEX, email) is not None


class Mail(Cog, name=COG_NAME):
    """Handle email functions"""

    def __init__(self, logger):
        """Init cog and connect to Amazon SES."""
        self.logger = logger
        self.client = connect()

    def send_email(self, recipient, subject, body_text):
        """Send plaintext email via Amazon SES.

        Args:
            recipient: String representing Email address of intended recipient.
            subject: String representing subject line of email.
            body_text: String representing body text of the email. Will be
                       treated as plaintext.

        Raises:
            MailError: If email fails to send.
        """
        LOG.debug(f"Sending SES email to {recipient}...")
        try:
            response = self.client.send_email(
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Body": {"Text": {"Charset": "UTF-8", "Data": body_text}},
                    "Subject": {"Charset": "UTF-8", "Data": subject},
                },
                Source=EMAIL,
            )
            LOG.info(f"SES email '{response['MessageId']}' " f"sent to '{recipient}'")
        except ClientError:
            raise MailError(recipient)


def connect():
    """Connect to Amazon SES.
    
    Required for all other methods to function.
    """
    LOG.debug("Logging in to Amazon SES...")
    client = boto3.client(
        "ses",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
    LOG.info("Logged in to Amazon SES")
    return client
