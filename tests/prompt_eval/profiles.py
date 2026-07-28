"""Фиксированные профили людей для prompt-eval генерации плана."""

PROFILES = [
    dict(key="new_gym_m", label="Новичок, зал, м, общая форма",
         goal="общая форма", sex="м", level="новичок",
         equip="всё оборудование зала", per_day=4, note="30 лет, здоров", injury=None),
    dict(key="mid_home_f", label="Средний, дом (гантели+резинки), ж, похудение",
         goal="похудение", sex="ж", level="средний",
         equip="гантели, резинки", per_day=4, note="34 года, сбросить вес", injury=None),
    dict(key="adv_gym_m", label="Продвинутый, зал, м, масса",
         goal="набор мышечной массы", sex="м", level="продвинутый",
         equip="всё оборудование зала", per_day=5, note="28 лет, 3 года стажа", injury=None),
    dict(key="new_mat_knee_f", label="Новичок, коврик, ж, тонус, болит колено",
         goal="тонус и осанка", sex="ж", level="новичок",
         equip="коврик", per_day=3, note="40 лет, болит правое колено", injury="колено"),
    dict(key="mid_street_m", label="Средний, улица турник/брусья, м, рельеф",
         goal="подтянуться и рельеф", sex="м", level="средний",
         equip="турник, брусья", per_day=4, note="26 лет", injury=None),
]

WEEKDAYS = [0, 2, 4]
