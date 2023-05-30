import logging
import sys

from django.core.management.base import BaseCommand
from django.db.transaction import atomic

from payments.models import Order

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sets state of old orders awaiting payment from "waiting" to "expired" or "confirmed".'

    @atomic
    def handle(self, *args, **options):
        logging.basicConfig(
            level = logging.INFO,
            format = "%(asctime)s %(message)s",
            datefmt = "%Y-%m-%d %H:%M:%S",
            stream = sys.stdout
        )
        logger.info('Handling too old unpaid orders...')
        num_of_expired_orders, num_of_confirmed_orders = Order.objects.update_expired()
        logger.info('Done, {} order(s) got expired.'.format(num_of_expired_orders))
        logger.info('{} paid order(s) got confirmed.'.format(num_of_confirmed_orders))
