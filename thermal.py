"""Steady-state heat transfer through flat and cylindrical insulation."""

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite, log, pi
from typing import Optional

SIGMA = 5.670374419e-8


@dataclass(frozen=True)
class Material:
    name: str
    points: tuple
    note: str = ""
    price_per_m2: Optional[float] = None
    price_reference_thickness_mm: Optional[float] = None

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Název materiálu nesmí být prázdný.")
        if not self.points:
            raise ValueError("Materiál musí mít alespoň jednu hodnotu lambda.")
        if (self.price_per_m2 is None) != (
            self.price_reference_thickness_mm is None
        ):
            raise ValueError("Zadejte cenu i tloušťku, pro kterou cena platí.")
        if self.price_per_m2 is not None and (
            not isfinite(self.price_per_m2)
            or self.price_per_m2 < 0
            or not isfinite(self.price_reference_thickness_mm)
            or self.price_reference_thickness_mm <= 0
        ):
            raise ValueError(
                "Cena musí být nezáporná a referenční tloušťka kladné konečné číslo."
            )
        last = None
        for temp, conductivity in self.points:
            if not isfinite(temp) or not isfinite(conductivity) or conductivity <= 0:
                raise ValueError("Teploty musí být konečné a lambda musí být kladná.")
            if temp <= -273.15:
                raise ValueError("Teplota musí být vyšší než absolutní nula.")
            if last is not None and temp <= last:
                raise ValueError("Teploty v tabulce musí být vzestupné a jedinečné.")
            last = temp

    def conductivity(self, temp):
        if len(self.points) == 1 or temp <= self.points[0][0]:
            return self.points[0][1]
        if temp >= self.points[-1][0]:
            return self.points[-1][1]
        i = bisect_right([p[0] for p in self.points], temp)
        t0, k0 = self.points[i - 1]
        t1, k1 = self.points[i]
        return k0 + (k1 - k0) * (temp - t0) / (t1 - t0)

    def integral(self, low, high):
        """Integral of piecewise-linear lambda(T), in W/m."""
        if low > high:
            return -self.integral(high, low)
        boundaries = [low] + [t for t, _ in self.points if low < t < high] + [high]
        return sum(
            (b - a) * (self.conductivity(a) + self.conductivity(b)) / 2
            for a, b in zip(boundaries, boundaries[1:])
        )


@dataclass(frozen=True)
class Layer:
    material: Material
    thickness: float  # m


def estimate_material_costs(geometry, layers, size, diameter=None):
    """Estimate layer costs from price per m² at a reference thickness.

    Cylindrical material area is measured at each layer's mean radius.
    """
    if not isfinite(size) or size <= 0:
        raise ValueError("Rozměr pro odhad ceny musí být kladný.")
    if geometry == "cylinder":
        if diameter is None or not isfinite(diameter) or diameter <= 0:
            raise ValueError("Vnitřní průměr pro odhad ceny musí být kladný.")
        radius = diameter / 2
    elif geometry == "flat":
        radius = None
    else:
        raise ValueError("Neznámá geometrie.")

    costs = []
    for layer in layers:
        if not isfinite(layer.thickness) or layer.thickness <= 0:
            raise ValueError("Tloušťky vrstev musí být kladné konečné číslo.")
        area = (
            size
            if geometry == "flat"
            else 2 * pi * size * (radius + layer.thickness / 2)
        )
        price = layer.material.price_per_m2
        costs.append(
            None
            if price is None
            else area
            * price
            * (layer.thickness * 1000)
            / layer.material.price_reference_thickness_mm
        )
        if geometry == "cylinder":
            radius += layer.thickness
    return tuple(costs)


@dataclass(frozen=True)
class Result:
    temperatures: tuple  # inner surface, interfaces, outer surface
    heat_rate: float  # W for the specified area or length
    heat_flux_outer: float  # W/m²
    outer_area: float  # m²
    warnings: tuple


def calculate(geometry, hot, ambient, layers, size, h, emissivity, diameter=None):
    """Solve with prescribed inner surface temperature and ambient surroundings.

    size is flat area in m² or cylinder length in m. The ambient temperature
    is also the effective surrounding radiative temperature.
    """
    values = (hot, ambient, size, h, emissivity)
    if not all(isfinite(x) for x in values):
        raise ValueError("Vstupy musí být konečná čísla.")
    if ambient <= -273.15 or hot <= -273.15:
        raise ValueError("Teploty musí být vyšší než absolutní nula.")
    if hot <= ambient:
        raise ValueError("Vnitřní teplota musí být vyšší než okolní teplota.")
    if size <= 0 or h < 0 or not 0 <= emissivity <= 1:
        raise ValueError("Rozměr musí být kladný, h nezáporné a emisivita mezi 0 a 1.")
    if h == 0 and emissivity == 0:
        raise ValueError("Proudění a sálání nemohou být současně nulové.")
    if not layers:
        raise ValueError("Přidejte alespoň jednu vrstvu.")
    if any(not isfinite(layer.thickness) or layer.thickness <= 0 for layer in layers):
        raise ValueError("Tloušťky vrstev musí být kladná konečná čísla.")
    if geometry not in ("flat", "cylinder"):
        raise ValueError("Neznámá geometrie.")
    if geometry == "cylinder" and (
        diameter is None or not isfinite(diameter) or diameter <= 0
    ):
        raise ValueError("Vnitřní průměr izolace musí být kladné konečné číslo.")

    factors = []
    if geometry == "flat":
        factors = [layer.thickness / size for layer in layers]
        outer_area = size
    else:
        radius = diameter / 2
        for layer in layers:
            next_radius = radius + layer.thickness
            factors.append(log(next_radius / radius) / (2 * pi * size))
            radius = next_radius
        outer_area = 2 * pi * radius * size

    def temperatures_for_heat(heat):
        temps = [hot]
        for layer, factor in zip(layers, factors):
            high = temps[-1]
            if layer.material.integral(ambient, high) <= heat * factor:
                temps.append(ambient)
                continue
            low = ambient
            for _ in range(70):
                mid = (low + high) / 2
                if layer.material.integral(mid, temps[-1]) > heat * factor:
                    low = mid
                else:
                    high = mid
            temps.append((low + high) / 2)
        return temps

    def surface_heat(temp):
        # Factored difference of fourth powers avoids cancellation near ambient.
        ts, ta = temp + 273.15, ambient + 273.15
        return outer_area * (temp - ambient) * (
            h + emissivity * SIGMA * (ts + ta) * (ts * ts + ta * ta)
        )

    low, high = 0.0, surface_heat(hot)
    for _ in range(80):
        heat = (low + high) / 2
        temps = temperatures_for_heat(heat)
        if heat > surface_heat(temps[-1]):
            high = heat
        else:
            low = heat
    heat = (low + high) / 2
    temps = temperatures_for_heat(heat)
    warnings = []
    for i, layer in enumerate(layers):
        points = layer.material.points
        if len(points) > 1 and (temps[i + 1] < points[0][0] - 1e-8 or temps[i] > points[-1][0] + 1e-8):
            warnings.append(
                f"Vrstva {i + 1} ({layer.material.name}): mimo tabulku lambda; "
                "použita nejbližší krajní hodnota."
            )
    return Result(tuple(temps), heat, heat / outer_area, outer_area, tuple(warnings))


def temperature_profile(geometry, layers, size, result, diameter=None, samples_per_layer=20):
    """Return (distance through wall in m, temperature in °C) profile samples."""
    if samples_per_layer < 1:
        raise ValueError("Počet vzorků na vrstvu musí být kladný.")
    if geometry == "cylinder":
        if diameter is None or diameter <= 0:
            raise ValueError("Vnitřní průměr izolace musí být kladný.")
        radius = diameter / 2
    elif geometry == "flat":
        radius = None
    else:
        raise ValueError("Neznámá geometrie.")

    profile = [(0.0, result.temperatures[0])]
    distance = 0.0
    for index, layer in enumerate(layers):
        inner_temperature = result.temperatures[index]
        outer_temperature = result.temperatures[index + 1]
        for sample in range(1, samples_per_layer + 1):
            segment = layer.thickness * sample / samples_per_layer
            if geometry == "flat":
                heat_integral = result.heat_rate * segment / size
            else:
                heat_integral = (
                    result.heat_rate
                    * log((radius + segment) / radius)
                    / (2 * pi * size)
                )
            low, high = outer_temperature, inner_temperature
            for _ in range(70):
                middle = (low + high) / 2
                if layer.material.integral(middle, inner_temperature) > heat_integral:
                    low = middle
                else:
                    high = middle
            temperature = outer_temperature if sample == samples_per_layer else (low + high) / 2
            profile.append((distance + segment, temperature))
        distance += layer.thickness
        if geometry == "cylinder":
            radius += layer.thickness
    return tuple(profile)
