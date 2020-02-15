from msrestazure.azure_active_directory import MSIAuthentication
from .sendgridemail import EmailClient
from .azurevmautostop import Subscription, VirtualMachine
import os
import itertools
import datetime
import logging
import azure.functions

email_api_key = os.environ.get('SENDGRID_API_KEY')
warning_email_from = os.environ.get('WARNING_EMAIL_FROM')
default_warning_email_to = os.environ.get('WARNING_EMAIL_TO')
default_inactivity_th_mins = float(os.environ.get(
    'INACTIVITY_THRESHOLD_MINUTES'))
default_post_warning_th_mins = float(
    os.environ.get('POST_WARNING_THRESHOLD_MINS'))
default_percentage_cpu_stdev_bas_pct = float(os.environ.get(
    'PERCENTAGE_CPU_STDEV_BASELINE_PERCENTAGE'))
default_network_out_stdev_bas_pct = float(os.environ.get(
    'NETWORK_OUT_STDEV_BASELINE_PERCENTAGE'))


def get_credentials():
    """
    Gets Azure AD auth credentials.
    """
    return MSIAuthentication()


def main(timer: azure.functions.TimerRequest) -> None:
    if timer.past_due:
        logging.info("The timer is past due!")
    credentials = get_credentials()
    email_client = EmailClient(email_api_key,
                               warning_email_from,
                               default_warning_email_to)
    virtual_machines = list(
        itertools.chain.from_iterable(
            [sub.get_virtual_machines(default_inactivity_th_mins, default_post_warning_th_mins,
                                      default_percentage_cpu_stdev_bas_pct, default_network_out_stdev_bas_pct)
             for sub in Subscription.get_subscriptions(credentials,
                                                       email_client)]
        )
    )
    utc_timestamp = datetime.datetime.utcnow().replace(
        tzinfo=datetime.timezone.utc)
    vms = [vm.stop(utc_timestamp) for vm in virtual_machines]
    logging.info(vms)
