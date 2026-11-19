import math
import unittest

from thermal import (
    Layer,
    Material,
    SIGMA,
    calculate,
    estimate_material_costs,
    temperature_profile,
)


class ThermalTests(unittest.TestCase):
    def test_flat_material_costs_scale_with_thickness_and_report_missing_prices(self):
        priced = Material(
            "priced", ((20, 0.1),), price_per_m2=847,
            price_reference_thickness_mm=100,
        )
        unpriced = Material("unpriced", ((20, 0.1),))
        layers = [
            Layer(priced, 0.05),
            Layer(priced, 0.25),
            Layer(unpriced, 0.1),
        ]
        costs = estimate_material_costs("flat", layers, 2)
        self.assertAlmostEqual(costs[0], 847)
        self.assertAlmostEqual(costs[1], 4235)
        self.assertIsNone(costs[2])

    def test_cylinder_material_cost_uses_mean_layer_radius(self):
        material = Material(
            "priced", ((20, 0.1),), price_per_m2=880,
            price_reference_thickness_mm=100,
        )
        layer = Layer(material, 0.1)
        costs = estimate_material_costs("cylinder", [layer], 2, diameter=1)
        expected_area = 2 * math.pi * 0.55 * 2
        self.assertAlmostEqual(costs[0], expected_area * 880)

    def test_material_cost_uses_each_material_reference_thickness(self):
        fiber = Material(
            "fiber", ((20, 0.1),), price_per_m2=847,
            price_reference_thickness_mm=50,
        )
        costs = estimate_material_costs("flat", [Layer(fiber, 0.05)], 2)
        self.assertAlmostEqual(costs[0], 1694)

    def test_material_price_must_be_finite_and_nonnegative(self):
        for price in (-1, float("nan"), float("inf")):
            with self.subTest(price=price), self.assertRaises(ValueError):
                Material(
                    "invalid price",
                    ((20, 0.1),),
                    price_per_m2=price,
                    price_reference_thickness_mm=100,
                )
        with self.assertRaises(ValueError):
            Material("incomplete price", ((20, 0.1),), price_per_m2=847)
        with self.assertRaises(ValueError):
            Material(
                "invalid reference thickness",
                ((20, 0.1),),
                price_per_m2=847,
                price_reference_thickness_mm=0,
            )

    def test_flat_constant_conductivity(self):
        layer = Layer(Material("constant", ((20, 0.1),)), 0.1)
        result = calculate("flat", 120, 20, [layer], 2, 10, 0)
        expected = 2 * 100 / (0.1 / 0.1 + 1 / 10)
        self.assertAlmostEqual(result.heat_rate, expected, places=8)
        self.assertAlmostEqual(result.temperatures[-1], 20 + expected / 20, places=8)
        self.assertAlmostEqual(result.heat_flux_outer, expected / 2, places=8)

    def test_cylinder_multilayer_constant_conductivity(self):
        layers = [Layer(Material("a", ((20, 0.1),)), 0.05), Layer(Material("b", ((20, 0.05),)), 0.25)]
        diameter, length, h = 0.5, 3, 5
        radius = diameter / 2
        area = 2 * math.pi * (radius + 0.3) * length
        resistance = (math.log((radius + 0.05) / radius) / (2 * math.pi * length * 0.1)
                      + math.log((radius + 0.3) / (radius + 0.05)) / (2 * math.pi * length * 0.05)
                      + 1 / (h * area))
        result = calculate("cylinder", 600, 20, layers, length, h, 0, diameter)
        self.assertAlmostEqual(result.heat_rate, 580 / resistance, places=8)
        self.assertAlmostEqual(result.temperatures[-1], 20 + result.heat_rate / (h * area), places=8)

    def test_variable_conductivity_and_radiation_balance(self):
        material = Material("variable", ((20, 0.04), (100, 0.08), (300, 0.18)))
        result = calculate("flat", 300, 20, [Layer(material, 0.2)], 1, 5, 0.8)
        surface = result.temperatures[-1]
        conduction = material.integral(surface, 300) / 0.2
        radiation = 0.8 * SIGMA * ((surface + 273.15)**4 - (20 + 273.15)**4)
        self.assertAlmostEqual(result.heat_rate, conduction, places=8)
        self.assertAlmostEqual(result.heat_rate, 5 * (surface - 20) + radiation, places=8)
        self.assertAlmostEqual(material.integral(20, 300), 30.8)
        profile = temperature_profile(
            "flat", [Layer(material, 0.2)], 1, result, samples_per_layer=4
        )
        for distance, temperature in profile:
            self.assertAlmostEqual(
                material.integral(temperature, 300), result.heat_rate * distance
            )

    def test_range_warnings_only_for_actual_temperatures(self):
        material = Material("limited", ((50, 0.1), (100, 0.2)))
        result = calculate("flat", 200, 20, [Layer(material, 0.1)], 1, 5, 0)
        self.assertEqual(len(result.warnings), 1)
        result = calculate("flat", 100, 20, [Layer(material, 0.1)], 1, 1, 0)
        self.assertEqual(result.warnings, ())

    def test_flat_temperature_profile(self):
        layer = Layer(Material("constant", ((20, 0.1),)), 0.1)
        result = calculate("flat", 120, 20, [layer], 2, 10, 0)
        profile = temperature_profile("flat", [layer], 2, result, samples_per_layer=2)
        self.assertEqual(len(profile), 3)
        self.assertAlmostEqual(profile[1][0], 0.05)
        self.assertAlmostEqual(profile[1][1], 120 - result.heat_rate * 0.05 / (2 * 0.1))
        self.assertAlmostEqual(profile[-1][1], result.temperatures[-1])

    def test_cylinder_temperature_profile(self):
        layer = Layer(Material("constant", ((20, 0.1),)), 0.1)
        length, diameter = 2, 1
        result = calculate("cylinder", 120, 20, [layer], length, 10, 0, diameter)
        profile = temperature_profile(
            "cylinder", [layer], length, result, diameter, samples_per_layer=2
        )
        expected = 120 - result.heat_rate * math.log(0.55 / 0.5) / (
            2 * math.pi * length * 0.1
        )
        self.assertAlmostEqual(profile[1][0], 0.05)
        self.assertAlmostEqual(profile[1][1], expected)
        self.assertAlmostEqual(profile[-1][1], result.temperatures[-1])

    def test_invalid_inputs(self):
        material = Material("constant", ((20, 0.1),))
        for args in [
            ("flat", 20, 20, [Layer(material, 0.1)], 1, 5, 0, None),
            ("flat", 100, 20, [], 1, 5, 0, None),
            ("flat", 100, 20, [Layer(material, 0.1)], 1, 0, 0, None),
            ("cylinder", 100, 20, [Layer(material, 0.1)], 1, 5, 0, 0),
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                calculate(*args)
        with self.assertRaises(ValueError):
            Material("bad", ((20, 0.1), (20, 0.2)))
        with self.assertRaises(ValueError):
            Material("bad", ((20, float("nan")),))


if __name__ == "__main__":
    unittest.main()
