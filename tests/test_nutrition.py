from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.models.nutrition import MealItem, WeightLog
from app.services.nutrition import daily_summary, day_bounds, owned_meal


def meal_payload(at='2026-09-14T12:00:00+03:00', calories='100.10'):
    return {
        'occurred_at': at, 'meal_type': 'lunch', 'original_description': 'Tavuk ve pilav',
        'items': [{'name': 'Tavuk', 'quantity': '200.00', 'unit': 'g', 'calories': calories,
                   'protein_g': '20.20', 'carbs_g': '0.30', 'fat_g': '3.40'}],
    }


def create(client, user, payload=None):
    response = client.post(f'/api/v1/users/{user}/meals', json=payload or meal_payload())
    assert response.status_code == 201, response.text
    return response.json()


def test_meal_crud_recalculates_without_stale_totals(client, users, nutrition_app):
    user = users[0]
    base = f'/api/v1/users/{user}'
    payload = meal_payload()
    payload['items'].append({**payload['items'][0], 'name': 'Pilav', 'calories': '0.20'})
    meal = create(client, user, payload)
    assert meal['totals'] == {'calories': '100.30', 'protein_g': '40.40', 'carbs_g': '0.60', 'fat_g': '6.80'}
    daily = lambda: client.get(base + '/nutrition/daily?day=2026-09-14').json()
    assert daily()['totals']['calories'] == '100.30'
    payload['items'][1]['calories'] = '50.25'
    changed = client.put(base + '/meals/' + meal['id'], json={**payload, 'expected_version': 1})
    assert changed.status_code == 200, changed.text
    assert changed.json()['totals']['calories'] == '150.35'
    assert changed.json()['version'] == 2
    assert daily()['totals']['calories'] == '150.35'
    assert client.put(base + '/meals/' + meal['id'], json={**payload, 'expected_version': 1}).status_code == 409
    # Item rows are the sole source even if changed directly through the ORM.
    with nutrition_app.state.session_factory() as session:
        item = session.scalar(select(MealItem).where(MealItem.user_id == user, MealItem.meal_id == meal['id'], MealItem.name == 'Pilav'))
        item.calories = Decimal('60.01')
        session.commit()
    assert client.get(base + '/meals/' + meal['id']).json()['totals']['calories'] == '160.11'
    assert daily()['totals']['calories'] == '160.11'
    other = create(client, user, meal_payload(calories='10.00'))
    assert client.delete(base + '/meals/' + meal['id']).status_code == 204
    assert daily()['totals']['calories'] == '10.00'
    assert client.get(base + '/meals/' + meal['id']).status_code == 404
    with nutrition_app.state.session_factory() as session:
        assert session.scalar(select(MealItem).where(MealItem.user_id == user, MealItem.meal_id == meal['id'])) is None
    client.delete(base + '/meals/' + other['id'])
    assert daily()['totals'] is None
    assert daily()['has_records'] is False


def test_istanbul_midnight_and_today(client, users, monkeypatch, nutrition_app):
    user = users[0]
    base = f'/api/v1/users/{user}'
    # Local: Sep 13 23:59:59, Sep 14 00:00, Sep 14 23:59:59, Sep 15 00:00.
    instants = ['2026-09-13T20:59:59Z', '2026-09-13T21:00:00Z', '2026-09-14T20:59:59Z', '2026-09-14T21:00:00Z']
    ids = [create(client, user, meal_payload(at, str(i + 1)))['id'] for i, at in enumerate(instants)]
    rows = client.get(base + '/meals?day=2026-09-14').json()
    assert {row['id'] for row in rows} == set(ids[1:3])
    assert client.get(base + '/nutrition/daily?day=2026-09-14').json()['totals']['calories'] == '5.00'
    frozen = datetime(2026, 9, 13, 21, 30, tzinfo=timezone.utc)
    monkeypatch.setattr('app.services.nutrition.utc_now', lambda: frozen)
    assert {row['id'] for row in client.get(base + '/meals/today').json()} == set(ids[1:3])
    assert client.get(base + '/nutrition/daily').json()['date'] == '2026-09-14'
    with nutrition_app.state.session_factory() as session:
        assert daily_summary(session, user, now=frozen).date == date(2026, 9, 14)
    start, end = day_bounds(date(2026, 9, 14), 'Europe/Istanbul')
    assert start == datetime(2026, 9, 13, 21, tzinfo=timezone.utc)
    assert end - start == timedelta(hours=24)


@pytest.mark.parametrize('day,hours', [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_dst_boundaries(day, hours):
    start, end = day_bounds(day, 'America/New_York')
    assert end - start == timedelta(hours=hours)


def test_week_missing_days_and_targets(client, users):
    user = users[0]
    base = f'/api/v1/users/{user}'
    client.put(base + '/profile', json={'calorie_target': 150, 'protein_target_g': 50})
    create(client, user, meal_payload('2026-09-08T00:00:00+03:00', '100'))
    create(client, user, meal_payload('2026-09-14T23:59:59+03:00', '200'))
    create(client, user, meal_payload('2026-09-07T23:59:59+03:00', '999'))
    create(client, user, meal_payload('2026-09-15T00:00:00+03:00', '999'))
    create(client, users[1], meal_payload(calories='999'))
    result = client.get(base + '/nutrition/weekly?end_day=2026-09-14').json()
    assert result['recorded_days'] == 2 and result['missing_days'] == 5
    assert result['average_over_recorded_days']['calories'] == '150.00'
    assert result['days_above_current_calorie_target'] == 1
    assert result['days_below_current_calorie_target'] == 1
    assert result['days'][1]['totals'] is None
    assert result['days'][1]['remaining_by_target']['calories'] is None
    assert result['days'][-1]['remaining_by_target']['calories'] == '-50.00'
    assert result['days'][-1]['remaining_by_target']['fat_g'] is None
    empty = client.get(base + '/nutrition/weekly?end_day=2025-01-01').json()
    assert empty['average_over_recorded_days'] is None
    assert empty['recorded_days'] == 0
    # An explicit recorded zero and a missing day must remain distinguishable.
    zero = meal_payload('2025-01-01T12:00:00Z', '0')
    create(client, user, zero)
    result = client.get(base + '/nutrition/weekly?end_day=2025-01-01').json()
    assert result['recorded_days'] == 1
    assert result['average_over_recorded_days']['calories'] == '0.00'


def test_scope_all_meal_and_weight_operations(client, users):
    a, b = users
    meal = create(client, b)
    weight_data = {'occurred_at': '2026-09-14T09:00:00Z', 'weight_kg': '97.80'}
    weight = client.post(f'/api/v1/users/{b}/weight-logs', json=weight_data).json()
    base = f'/api/v1/users/{a}'
    for method in ('get', 'delete', 'put'):
        for path, payload in [(f"/meals/{meal['id']}", {**meal_payload(), 'expected_version': 1}), (f"/weight-logs/{weight['id']}", weight_data)]:
            kwargs = {'json': payload} if method == 'put' else {}
            assert getattr(client, method)(base + path, **kwargs).status_code == 404
    for path in ('/meals', '/meals?day=2026-09-14', '/meals/today', '/weight-logs'):
        assert client.get(base + path).json() == []
    assert client.get(base + '/weight-logs/current').json() is None
    assert client.get(base + '/nutrition/daily?day=2026-09-14').json()['totals'] is None
    assert client.get(base + '/nutrition/weekly?end_day=2026-09-14').json()['recorded_days'] == 0
    assert client.get(f"/api/v1/users/{b}/meals/{meal['id']}").status_code == 200
    assert client.get(f"/api/v1/users/{b}/weight-logs/{weight['id']}").status_code == 200
    forged = meal_payload(); forged['items'][0]['user_id'] = b
    assert client.post(base + '/meals', json=forged).status_code == 422


@pytest.mark.parametrize('field,value', [
    ('calories', '-0.01'), ('protein_g', '-1'), ('carbs_g', '-1'), ('fat_g', '-1'),
    ('quantity', '0'), ('calories', 'NaN'), ('calories', 'Infinity'), ('calories', '0.001'),
])
def test_invalid_item_numbers(client, users, field, value):
    payload = meal_payload(); payload['items'][0][field] = value
    assert client.post(f'/api/v1/users/{users[0]}/meals', json=payload).status_code == 422


@pytest.mark.parametrize('value', ['-1', '0', 'NaN', 'Infinity', '97.801'])
def test_invalid_weights(client, users, value):
    response = client.post(f'/api/v1/users/{users[0]}/weight-logs', json={'occurred_at': '2026-09-14T12:00:00Z', 'weight_kg': value})
    assert response.status_code == 422


def test_naive_time_and_empty_items_rejected(client, users):
    base = f'/api/v1/users/{users[0]}'
    assert client.post(base + '/meals', json=meal_payload('2026-09-14T12:00:00')).status_code == 422
    payload = meal_payload(); payload['items'] = []
    assert client.post(base + '/meals', json=payload).status_code == 422
    assert client.post(base + '/weight-logs', json={'occurred_at': '2026-09-14T12:00:00', 'weight_kg': '90'}).status_code == 422


def test_weight_crud_latest_measurement_not_insert_order(client, users):
    base = f'/api/v1/users/{users[0]}/weight-logs'
    new = client.post(base, json={'occurred_at': '2026-09-14T12:00:00+03:00', 'weight_kg': '97.80'})
    assert new.status_code == 201
    new = new.json()
    old = client.post(base, json={'occurred_at': '2026-09-13T12:00:00Z', 'weight_kg': '98.10'}).json()
    assert client.get(base + '/current').json()['id'] == new['id']
    assert client.get(base).json()[0]['id'] == new['id']
    result = client.put(base + '/' + old['id'], json={'occurred_at': '2026-09-15T12:00:00Z', 'weight_kg': '97.50'})
    assert result.status_code == 200
    assert client.get(base + '/current').json()['weight_kg'] == '97.50'
    assert client.delete(base + '/' + old['id']).status_code == 204
    assert client.get(base + '/current').json()['id'] == new['id']
    client.delete(base + '/' + new['id'])
    assert client.get(base + '/current').json() is None


def test_cross_user_item_fk_and_database_nonnegative(client, users, nutrition_app):
    meal = create(client, users[0])
    with nutrition_app.state.session_factory() as session:
        item = MealItem(user_id=users[1], meal_id=meal['id'], **meal_payload()['items'][0])
        session.add(item)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        for field in ('calories', 'protein_g', 'carbs_g', 'fat_g', 'quantity'):
            with pytest.raises(IntegrityError):
                session.execute(text(f'UPDATE meal_items SET {field} = -1 WHERE user_id = :user'), {'user': users[0]})
            session.rollback()
        # SQLite affinity alone would permit a floating-point value: CHECK rejects it.
        with pytest.raises(IntegrityError):
            session.execute(text('UPDATE meal_items SET calories = 1.5 WHERE user_id = :user'), {'user': users[0]})
        session.rollback()
        session.add(WeightLog(user_id=users[0], occurred_at=datetime.now(timezone.utc), weight_kg=Decimal('-1')))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.execute(text('SELECT calories FROM meal_items WHERE user_id = :user'), {'user': users[0]}).scalar() == 10010


def test_concurrent_meal_update_rejected(client, users, nutrition_app):
    meal = create(client, users[0])
    with nutrition_app.state.session_factory() as a, nutrition_app.state.session_factory() as b:
        first = owned_meal(a, users[0], meal['id'])
        second = owned_meal(b, users[0], meal['id'])
        first.original_description = 'Birinci düzeltme'; a.commit()
        second.original_description = 'Eski sürüm düzeltmesi'
        with pytest.raises(StaleDataError):
            b.commit()
        b.rollback()


def test_moving_meal_between_days(client, users):
    base = f'/api/v1/users/{users[0]}'
    meal = create(client, users[0])
    payload = meal_payload('2026-09-15T00:00:00+03:00')
    result = client.put(base + '/meals/' + meal['id'], json={**payload, 'expected_version': meal['version']})
    assert result.status_code == 200
    assert client.get(base + '/nutrition/daily?day=2026-09-14').json()['totals'] is None
    assert client.get(base + '/nutrition/daily?day=2026-09-15').json()['totals']['calories'] == '100.10'
