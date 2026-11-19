"""Desktop insulation calculator; run with python app.py."""

import json
import math
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from thermal import (
    Layer,
    Material,
    calculate,
    estimate_material_costs,
    temperature_profile,
)

MATERIALS_PATH = Path(__file__).with_name("materials.json")
PROFILE_SAMPLES_PER_LAYER = 20


def read_materials():
    with MATERIALS_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    materials = [
        Material(
            item["name"],
            tuple(tuple(p) for p in item["points"]),
            item.get("note", ""),
            item.get("price_per_m2"),
            item.get("price_reference_thickness_mm"),
        )
        for item in data
    ]
    if not materials or len({m.name for m in materials}) != len(materials):
        raise ValueError("Databáze materiálů musí obsahovat jedinečné názvy.")
    return materials


def save_materials(materials):
    data = [
        {
            "name": m.name,
            "points": m.points,
            "note": m.note,
            "price_per_m2": m.price_per_m2,
            "price_reference_thickness_mm": m.price_reference_thickness_mm,
        }
        for m in materials
    ]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=MATERIALS_PATH.parent, delete=False) as file:
            temporary = file.name
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, MATERIALS_PATH)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def number(text):
    return float(text.strip().replace(",", "."))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Výpočet izolace")
        self.geometry("1120x780")
        self.minsize(850, 600)
        self.materials = read_materials()
        self.layers = []
        self.inputs = {}
        self.geometry_type = tk.StringVar(value="cylinder")
        self.material_var = tk.StringVar(value=self.materials[0].name)
        self.thickness_var = tk.StringVar(value="50")
        self.build()
        self.add_layer()
        if len(self.materials) > 1:
            self.material_var.set(self.materials[1].name)
            self.thickness_var.set("250")
            self.add_layer()

    def build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        settings = ttk.LabelFrame(self, text="Zadání", padding=8)
        settings.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text="Geometrie").grid(row=0, column=0, sticky="w")
        choice = ttk.Frame(settings)
        choice.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(choice, text="Válec", variable=self.geometry_type, value="cylinder", command=self.update_geometry).pack(side="left")
        ttk.Radiobutton(choice, text="Rovina", variable=self.geometry_type, value="flat", command=self.update_geometry).pack(side="left")
        fields = [
            ("hot", "Teplota vnitřního povrchu [°C]", "600"),
            ("ambient", "Teplota okolí a okolních ploch [°C]", "20"),
            ("diameter", "Vnitřní průměr izolace [mm]", "500"),
            ("size", "Délka válce [m]", "1"),
            ("h", "Součinitel proudění h [W/(m²·K)]", "5"),
            ("emissivity", "Emisivita povrchu [0–1]", "0.8"),
        ]
        for row, (key, label, default) in enumerate(fields, 1):
            widget = ttk.Label(settings, text=label)
            widget.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(settings, textvariable=var, width=15)
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.inputs[key] = (var, widget, entry)

        layer_frame = ttk.LabelFrame(self, text="Vrstvy od vnitřní k vnější", padding=8)
        layer_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        layer_frame.columnconfigure(0, weight=1)
        layer_frame.rowconfigure(0, weight=1)
        self.layer_list = tk.Listbox(layer_frame, height=6, exportselection=False)
        self.layer_list.grid(row=0, column=0, columnspan=4, sticky="nsew")
        ttk.Label(layer_frame, text="Materiál").grid(row=1, column=0, sticky="w")
        self.material_combo = ttk.Combobox(layer_frame, textvariable=self.material_var, state="readonly")
        self.material_combo.grid(row=2, column=0, sticky="ew")
        self.refresh_materials()
        ttk.Entry(layer_frame, textvariable=self.thickness_var, width=8).grid(row=2, column=1, padx=4)
        ttk.Label(layer_frame, text="mm").grid(row=2, column=2)
        ttk.Button(layer_frame, text="Přidat", command=self.add_layer).grid(row=2, column=3, padx=4)
        buttons = ttk.Frame(layer_frame)
        buttons.grid(row=3, column=0, columnspan=4, sticky="w", pady=6)
        ttk.Button(buttons, text="Odebrat", command=self.remove_layer).pack(side="left")
        ttk.Button(buttons, text="Nahoru", command=lambda: self.move_layer(-1)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Dolů", command=lambda: self.move_layer(1)).pack(side="left")
        ttk.Button(buttons, text="Materiály…", command=self.edit_materials).pack(side="left", padx=4)
        ttk.Button(layer_frame, text="Vypočítat", command=self.run_calculation).grid(row=4, column=0, columnspan=4, sticky="ew")

        output = ttk.LabelFrame(self, text="Výsledky a řez stěnou", padding=8)
        output.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(0, 8), pady=8)
        output.rowconfigure(1, weight=1)
        output.columnconfigure(0, weight=1)
        self.result = tk.Text(output, height=13, wrap="word")
        self.result.grid(row=0, column=0, sticky="nsew")
        self.canvas = tk.Canvas(output, background="white", highlightthickness=1, highlightbackground="#cccccc")
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.last_drawing = None
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.update_geometry()
        self.result.insert("1.0", "Orientační příklad: doplňte skutečný průměr, povrch a vlastnosti materiálů a klikněte na Vypočítat.\n\nPředvyplněné materiály nejsou ověřené údaje konkrétních výrobků.")
        for var, _, _ in self.inputs.values():
            var.trace_add("write", lambda *_: self.invalidate())

    def update_geometry(self):
        cylinder = self.geometry_type.get() == "cylinder"
        self.inputs["diameter"][2].configure(state="normal" if cylinder else "disabled")
        self.inputs["size"][1].configure(text="Délka válce [m]" if cylinder else "Plocha stěny [m²]")
        self.invalidate()

    def invalidate(self):
        if hasattr(self, "result"):
            self.result.delete("1.0", "end")
            self.result.insert("1.0", "Zadání se změnilo. Pro aktuální výsledek klikněte na Vypočítat.")
            self.last_drawing = None
            self.canvas.delete("all")

    def refresh_materials(self):
        self.material_combo["values"] = [m.name for m in self.materials]

    def refresh_layers(self):
        self.layer_list.delete(0, "end")
        for index, layer in enumerate(self.layers, 1):
            self.layer_list.insert("end", f"{index}. {layer.material.name}  —  {layer.thickness * 1000:g} mm")

    def add_layer(self):
        try:
            thickness = number(self.thickness_var.get()) / 1000
            if not math.isfinite(thickness) or thickness <= 0:
                raise ValueError("Tloušťka musí být kladné konečné číslo.")
            material = next(m for m in self.materials if m.name == self.material_var.get())
        except (ValueError, StopIteration) as error:
            messagebox.showerror("Neplatná vrstva", str(error) or "Vyberte materiál.", parent=self)
            return
        self.layers.append(Layer(material, thickness))
        self.refresh_layers()
        self.invalidate()

    def remove_layer(self):
        selected = self.layer_list.curselection()
        if selected:
            del self.layers[selected[0]]
            self.refresh_layers()
            self.invalidate()

    def move_layer(self, direction):
        selected = self.layer_list.curselection()
        if selected:
            i = selected[0]
            j = i + direction
            if 0 <= j < len(self.layers):
                self.layers[i], self.layers[j] = self.layers[j], self.layers[i]
                self.refresh_layers()
                self.layer_list.selection_set(j)
                self.invalidate()

    def edit_materials(self):
        MaterialEditor(self)

    def run_calculation(self):
        try:
            vals = {key: number(value[0].get()) for key, value in self.inputs.items() if key != "diameter"}
            diameter = number(self.inputs["diameter"][0].get()) / 1000 if self.geometry_type.get() == "cylinder" else None
            result = calculate(self.geometry_type.get(), vals["hot"], vals["ambient"], self.layers, vals["size"], vals["h"], vals["emissivity"], diameter)
        except (ValueError, OverflowError) as error:
            self.invalidate()
            messagebox.showerror("Výpočet se nezdařil", str(error), parent=self)
            return
        inner_area = (
            vals["size"]
            if self.geometry_type.get() == "flat"
            else math.pi * diameter * vals["size"]
        )
        overall_u = result.heat_rate / (
            inner_area * (vals["hot"] - vals["ambient"])
        )
        overall_r = 1 / overall_u
        layer_costs = estimate_material_costs(
            self.geometry_type.get(), self.layers, vals["size"], diameter
        )
        known_cost = sum(cost for cost in layer_costs if cost is not None)
        missing_price = any(cost is None for cost in layer_costs)
        lines = [
            f"Vnější povrch: {result.temperatures[-1]:.1f} °C",
            f"Celková tepelná ztráta: {result.heat_rate:.1f} W",
            f"Celkový součinitel prostupu tepla U: {overall_u:.4g} W/(m²·K)",
            f"Celkový tepelný odpor R: {overall_r:.4g} m²·K/W",
            f"Hustota toku na vnějším povrchu: {result.heat_flux_outer:.1f} W/m²",
            f"Vnější plocha: {result.outer_area:.3f} m²",
        ]
        if self.geometry_type.get() == "cylinder":
            lines.append(f"Ztráta na metr délky: {result.heat_rate / vals['size']:.1f} W/m")
        lines.append("\nCena materiálu bez DPH (bez prořezu a montáže):")
        for index, (layer, cost) in enumerate(zip(self.layers, layer_costs), 1):
            amount = "cena nezadána" if cost is None else f"{cost:,.0f} Kč".replace(",", " ")
            lines.append(f"  Vrstva {index} ({layer.material.name}): {amount}")
        total_label = "Oceněný součet" if missing_price else "Celkem"
        total_note = " (neúplné)" if missing_price else ""
        lines.append(
            f"  {total_label}: {known_cost:,.0f} Kč{total_note}".replace(",", " ")
        )
        lines.append("\nTeploty rozhraní:")
        lines.append(f"  Vnitřní povrch: {result.temperatures[0]:.1f} °C")
        for i, layer in enumerate(self.layers):
            lines.append(f"  Za vrstvou {i + 1} ({layer.material.name}): {result.temperatures[i + 1]:.1f} °C")
        lines.append("\nPoužijte ověřené lambda(T) a zkontrolujte přípustné teploty jednotlivých výrobků.")
        lines.extend(result.warnings)
        self.result.delete("1.0", "end")
        self.result.insert("1.0", "\n".join(lines))
        profile = temperature_profile(
            self.geometry_type.get(),
            self.layers,
            vals["size"],
            result,
            diameter,
            samples_per_layer=PROFILE_SAMPLES_PER_LAYER,
        )
        self.last_drawing = (self.geometry_type.get(), diameter, tuple(self.layers), result, profile)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        if not self.last_drawing:
            return
        geometry, diameter, layers, result, profile = self.last_drawing
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        colors = ["#f3d9a4", "#e7a65a", "#b8c5a1", "#a9c5d5", "#d0b1c9"]
        section_bottom = max(125, height * 0.32)
        self.canvas.create_text(8, 8, anchor="nw", text="Řez stěnou", font=("TkDefaultFont", 10, "bold"))
        if geometry == "cylinder":
            outer = diameter / 2 + sum(layer.thickness for layer in layers)
            scale = min(width * 0.38, section_bottom * 0.38) / outer
            cx, cy = width / 2, section_bottom / 2 + 8
            radii = [diameter / 2]
            for layer in layers:
                radii.append(radii[-1] + layer.thickness)
            for i in reversed(range(len(layers))):
                radius = radii[i + 1] * scale
                self.canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, fill=colors[i % len(colors)], outline="#777777")
            radius = radii[0] * scale
            self.canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, fill="white", outline="#777777")
            self.canvas.create_text(cx, cy, text="vnitřek")
        else:
            total = sum(layer.thickness for layer in layers)
            left, right = width * 0.1, width * 0.9
            top, bottom = 38, section_bottom - 15
            x = left
            for i, layer in enumerate(layers):
                next_x = x + (right-left) * layer.thickness / total
                self.canvas.create_rectangle(x, top, next_x, bottom, fill=colors[i % len(colors)], outline="#777777")
                x = next_x
            self.canvas.create_text(left, top - 15, anchor="w", text="vnitřek → okolí")
        self.canvas.create_text(
            8, section_bottom, anchor="nw",
            text="Teplotní a λ průběh skrz vrstvy", font=("TkDefaultFont", 10, "bold")
        )

        plot_left, plot_right = 58, width - 62
        plot_top, plot_bottom = section_bottom + 30, height - 70
        if plot_right <= plot_left or plot_bottom <= plot_top:
            return
        temperatures = [temperature for _, temperature in profile]
        temperature_minimum, temperature_maximum = min(temperatures), max(temperatures)
        temperature_padding = max((temperature_maximum - temperature_minimum) * 0.08, 1)
        temperature_minimum -= temperature_padding
        temperature_maximum += temperature_padding
        conductivity_profiles = []
        profile_offset = 0
        for layer in layers:
            layer_profile = profile[
                profile_offset:profile_offset + PROFILE_SAMPLES_PER_LAYER + 1
            ]
            conductivity_profiles.append(
                [
                    (distance, layer.material.conductivity(temperature))
                    for distance, temperature in layer_profile
                ]
            )
            profile_offset += PROFILE_SAMPLES_PER_LAYER
        conductivities = [
            conductivity
            for layer_profile in conductivity_profiles
            for _, conductivity in layer_profile
        ]
        conductivity_minimum, conductivity_maximum = min(conductivities), max(conductivities)
        conductivity_padding = max(
            (conductivity_maximum - conductivity_minimum) * 0.08,
            conductivity_maximum * 0.04,
            0.001,
        )
        conductivity_minimum = max(0, conductivity_minimum - conductivity_padding)
        conductivity_maximum += conductivity_padding
        total_thickness = profile[-1][0]

        def chart_x(distance):
            return plot_left + (plot_right - plot_left) * distance / total_thickness

        def chart_y(temperature):
            return plot_bottom - (plot_bottom - plot_top) * (
                temperature - temperature_minimum
            ) / (temperature_maximum - temperature_minimum)

        def chart_y_conductivity(conductivity):
            return plot_bottom - (plot_bottom - plot_top) * (
                conductivity - conductivity_minimum
            ) / (conductivity_maximum - conductivity_minimum)

        for tick in range(5):
            fraction = tick / 4
            y = plot_bottom - (plot_bottom - plot_top) * fraction
            temperature = temperature_minimum + (
                temperature_maximum - temperature_minimum
            ) * fraction
            conductivity = conductivity_minimum + (
                conductivity_maximum - conductivity_minimum
            ) * fraction
            precision = 1 if temperature_maximum - temperature_minimum < 10 else 0
            self.canvas.create_line(plot_left, y, plot_right, y, fill="#e5e5e5")
            self.canvas.create_text(
                plot_left - 7, y, anchor="e", text=f"{temperature:.{precision}f} °C",
                fill="#c0392b", font=("TkDefaultFont", 8)
            )
            self.canvas.create_text(
                plot_right + 7, y, anchor="w", text=f"{conductivity:.3f}",
                fill="#2471a3", font=("TkDefaultFont", 8)
            )

        distance = 0.0
        boundaries = [0.0]
        for layer in layers:
            distance += layer.thickness
            boundaries.append(distance)
        for index, boundary in enumerate(boundaries):
            x = chart_x(boundary)
            self.canvas.create_line(x, plot_top, x, plot_bottom, fill="#d0d0d0", dash=(2, 3))
            if index < len(boundaries) - 1:
                self.canvas.create_rectangle(
                    x, plot_bottom + 18, chart_x(boundaries[index + 1]), plot_bottom + 32,
                    fill=colors[index % len(colors)], outline="#777777"
                )
                self.canvas.create_text(
                    (x + chart_x(boundaries[index + 1])) / 2, plot_bottom + 25,
                    text=str(index + 1), font=("TkDefaultFont", 8)
                )
        self.canvas.create_line(plot_left, plot_top, plot_left, plot_bottom, fill="#555555")
        self.canvas.create_line(plot_right, plot_top, plot_right, plot_bottom, fill="#2471a3")
        self.canvas.create_line(plot_left, plot_bottom, plot_right, plot_bottom, fill="#555555")
        coordinates = []
        for distance, temperature in profile:
            coordinates.extend((chart_x(distance), chart_y(temperature)))
        self.canvas.create_line(*coordinates, fill="#c0392b", width=2)
        for layer_profile in conductivity_profiles:
            conductivity_coordinates = []
            for distance, conductivity in layer_profile:
                conductivity_coordinates.extend(
                    (chart_x(distance), chart_y_conductivity(conductivity))
                )
            self.canvas.create_line(
                *conductivity_coordinates, fill="#2471a3", width=2
            )
        distance = 0.0
        interface_distances = [0.0]
        for layer in layers:
            distance += layer.thickness
            interface_distances.append(distance)
        for distance, temperature in zip(interface_distances, result.temperatures):
            x, y = chart_x(distance), chart_y(temperature)
            self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#c0392b", outline="white")
        self.canvas.create_text(
            plot_left, plot_bottom + 7, anchor="nw", text="0",
            fill="#555555", font=("TkDefaultFont", 8)
        )
        self.canvas.create_text(
            plot_right, plot_bottom + 7, anchor="ne", text=f"{total_thickness * 1000:g} mm",
            fill="#555555", font=("TkDefaultFont", 8)
        )
        self.canvas.create_text(
            (plot_left + plot_right) / 2, height - 8, anchor="s",
            text="Vzdálenost od vnitřního povrchu [mm]", fill="#555555",
            font=("TkDefaultFont", 8)
        )
        self.canvas.create_text(
            width - 8, (plot_top + plot_bottom) / 2, text="λ [W/(m·K)]",
            fill="#2471a3", font=("TkDefaultFont", 8), angle=90
        )


class MaterialEditor(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Materiály")
        self.geometry("620x600")
        self.transient(app)
        self.grab_set()
        self.columnconfigure(1, weight=1)
        self.rowconfigure(5, weight=1)
        ttk.Label(self, text="Materiál").grid(row=0, column=0, sticky="w", padx=8, pady=5)
        self.selected = tk.StringVar(value=app.material_var.get())
        self.combo = ttk.Combobox(self, textvariable=self.selected, values=[m.name for m in app.materials], state="readonly")
        self.combo.grid(row=0, column=1, sticky="ew", padx=8)
        self.combo.bind("<<ComboboxSelected>>", lambda event: self.load())
        ttk.Label(self, text="Název").grid(row=1, column=0, sticky="w", padx=8)
        self.name = ttk.Entry(self)
        self.name.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(self, text="Poznámka").grid(row=2, column=0, sticky="w", padx=8)
        self.note = ttk.Entry(self)
        self.note.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(self, text="Cena [Kč/m², bez DPH]").grid(row=3, column=0, sticky="w", padx=8)
        self.price = ttk.Entry(self)
        self.price.grid(row=3, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(self, text="Referenční tloušťka ceny [mm]").grid(row=4, column=0, sticky="w", padx=8)
        self.price_thickness = ttk.Entry(self)
        self.price_thickness.grid(row=4, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(self, text="Teplota [°C]; lambda [W/(m·K)]\nJedna dvojice na řádek.\nPro konstantní lambda zadejte jeden řádek.").grid(row=5, column=0, sticky="nw", padx=8)
        self.points = tk.Text(self, height=10, width=28)
        self.points.grid(row=5, column=1, sticky="nsew", padx=8, pady=4)
        buttons = ttk.Frame(self)
        buttons.grid(row=6, column=0, columnspan=2, pady=8)
        ttk.Button(buttons, text="Nový", command=self.clear).pack(side="left", padx=3)
        ttk.Button(buttons, text="Uložit", command=self.save).pack(side="left", padx=3)
        ttk.Button(buttons, text="Zavřít", command=self.destroy).pack(side="left", padx=3)
        self.load()

    def clear(self):
        self.selected.set("")
        self.name.delete(0, "end")
        self.note.delete(0, "end")
        self.price.delete(0, "end")
        self.price_thickness.delete(0, "end")
        self.points.delete("1.0", "end")

    def load(self):
        material = next((m for m in self.app.materials if m.name == self.selected.get()), None)
        if material:
            self.name.delete(0, "end")
            self.name.insert(0, material.name)
            self.note.delete(0, "end")
            self.note.insert(0, material.note)
            self.price.delete(0, "end")
            self.price_thickness.delete(0, "end")
            if material.price_per_m2 is not None:
                self.price.insert(0, f"{material.price_per_m2:g}")
                self.price_thickness.insert(
                    0, f"{material.price_reference_thickness_mm:g}"
                )
            self.points.delete("1.0", "end")
            self.points.insert("1.0", "\n".join(f"{t:g}; {k:g}" for t, k in material.points))

    def save(self):
        try:
            points = []
            for line in self.points.get("1.0", "end").splitlines():
                if line.strip():
                    parts = line.split(";")
                    if len(parts) != 2:
                        raise ValueError("Každý řádek musí obsahovat teplotu a lambda oddělené středníkem.")
                    points.append(tuple(number(part) for part in parts))
            price_text = self.price.get().strip()
            price = number(price_text) if price_text else None
            price_thickness_text = self.price_thickness.get().strip()
            price_thickness = (
                number(price_thickness_text) if price_thickness_text else None
            )
            material = Material(
                self.name.get().strip(),
                tuple(points),
                self.note.get().strip(),
                price,
                price_thickness,
            )
            old_name = self.selected.get()
            if any(m.name == material.name and m.name != old_name for m in self.app.materials):
                raise ValueError("Materiál s tímto názvem již existuje.")
            materials = [material if m.name == old_name else m for m in self.app.materials]
            if not old_name:
                materials.append(material)
            save_materials(materials)
        except (ValueError, OSError) as error:
            messagebox.showerror("Materiál nelze uložit", str(error), parent=self)
            return
        self.app.materials = materials
        self.app.layers = [Layer(material if layer.material.name == old_name else layer.material, layer.thickness) for layer in self.app.layers]
        self.app.refresh_materials()
        self.app.refresh_layers()
        self.app.material_var.set(material.name)
        self.app.invalidate()
        self.selected.set(material.name)
        self.combo["values"] = [m.name for m in materials]


if __name__ == "__main__":
    try:
        app = App()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Chyba databáze materiálů", str(error), parent=root)
        root.destroy()
    else:
        app.mainloop()
