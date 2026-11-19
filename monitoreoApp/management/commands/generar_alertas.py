from django.core.management.base import BaseCommand

from monitoreoApp.services import generar_alertas


class Command(BaseCommand):
    help = 'Revisa vencimientos, evidencias pendientes y avance bajo el umbral, y genera las alertas correspondientes.'

    def handle(self, *args, **options):
        creadas = generar_alertas()
        self.stdout.write(self.style.SUCCESS(f'Alertas nuevas generadas: {creadas}'))
