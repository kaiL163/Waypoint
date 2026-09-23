import unittest
from app.uploads import csv_rows, decode, beeline_request


class UploadTests(unittest.TestCase):
    def test_cp1251_and_semicolon(self):
        body = 'Заявка;Тип заявки HD;Адрес;Начало;Окончание;Широта;Долгота\n1;Авария;Москва;09:00;12:00;55.75;37.61'
        self.assertEqual(csv_rows(decode(body.encode('cp1251')))[0]['Адрес'], 'Москва')

    def test_norm_excludes_travel(self):
        row = {'Заявка': '1', 'Тип заявки HD': 'Подключение', 'Адрес': 'Москва', 'Начало': '09:00', 'Окончание': '12:00', 'Широта': '55.75', 'Долгота': '37.61'}
        self.assertEqual(beeline_request(row)['durationMinutes'], 70)
