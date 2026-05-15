// Copyright (c) 2026, BT ERP and contributors
// For license information, please see license.txt

function get_other_serials(frm, cdn) {
	return (frm.doc.items || [])
		.filter((row) => row.name !== cdn && row.serial_number)
		.map((row) => row.serial_number);
}

function bt_barcode_generate_row(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	if (!row.item_code) {
		frappe.msgprint(__("Please set Item Code first."));
		return;
	}
	const other_serials = get_other_serials(frm, cdn);
	if (
		row.serial_number &&
		!row.serial_number.includes("{") &&
		!other_serials.includes(row.serial_number)
	) {
		frappe.msgprint(__("Serial number already set."));
		return;
	}
	frappe.call({
		method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.generate_barcode",
		args: {
			item_code: row.item_code,
			idx: row.idx,
			production_plan: frm.doc.production_plan || "",
			posting_date: frm.doc.posting_date,
			existing_serials: JSON.stringify(other_serials),
		},
		callback(r) {
			if (!r.exc && r.message) {
				frappe.model.set_value(cdt, cdn, "serial_number", r.message);
				frappe.model.set_value(cdt, cdn, "barcode", r.message);
				frm.refresh_field("items");
				inject_grid_barcode_buttons(frm);
			}
		},
	});
}

function inject_grid_barcode_buttons(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid) {
		return;
	}

	const render_button = (grid_row) => {
		if (!grid_row?.doc) {
			return;
		}
		const $cell = $(grid_row.row).find('[data-fieldname="generate_barcode"]');
		if (!$cell.length) {
			return;
		}
		const $static = $cell.find(".static-area");
		$static.html(
			`<button type="button" class="btn btn-xs btn-default btn-generate-barcode-item">
				${__("Generate Barcode")}
			</button>`
		);
		$static.find(".btn-generate-barcode-item").on("click", function (e) {
			e.preventDefault();
			e.stopPropagation();
			bt_barcode_generate_row(frm, grid_row.doc.doctype, grid_row.doc.name);
		});
	};

	(grid.grid_rows || []).forEach(render_button);

	if (!grid._barcode_buttons_hooked) {
		grid._barcode_buttons_hooked = true;
		const grid_refresh = grid.refresh.bind(grid);
		grid.refresh = function (...args) {
			const out = grid_refresh(...args);
			setTimeout(() => inject_grid_barcode_buttons(frm), 0);
			return out;
		};
	}
}

frappe.ui.form.on("BT Barcode", {
	refresh(frm) {
		inject_grid_barcode_buttons(frm);
	},
	production_plan(frm) {
		if (!frm.doc.production_plan) {
			frm.clear_table("items");
			frm.clear_table("production_plans");
			frm.refresh_field("items");
			frm.refresh_field("production_plans");
			return;
		}
		frappe.call({
			method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.resolve_production_plan_data",
			args: {
				production_plan: frm.doc.production_plan,
				posting_date: frm.doc.posting_date,
			},
			callback(r) {
				if (r.exc || !r.message) {
					return;
				}
				const { base, plans, items, sales_order } = r.message;
				if (base && base !== frm.doc.production_plan) {
					frm.set_value("production_plan", base);
				}
				frm.clear_table("production_plans");
				(plans || []).forEach((plan) => {
					frm.add_child("production_plans", { production_plan: plan });
				});
				frm.refresh_field("production_plans");
				frm.clear_table("items");
				(items || []).forEach((row) => {
					frm.add_child("items", {
						item_code: row.item_code,
						item_name: row.item_name,
						customer_ref_code: row.customer_ref_code,
						ref_code: row.customer_ref_code,
						qty: row.qty,
						uom: row.uom,
						serial_number: row.serial_number,
					});
				});
				frm.refresh_field("items");
				inject_grid_barcode_buttons(frm);
				if (sales_order) {
					frm.set_value("sales_order", sales_order);
				}
				if (!plans || !plans.length) {
					frappe.msgprint(
						__("No Production Plans found for {0}", [base || frm.doc.production_plan])
					);
				}
			},
		});
	},
});

frappe.ui.form.on("BT Barcode Item", {
	generate_barcode(frm, cdt, cdn) {
		bt_barcode_generate_row(frm, cdt, cdn);
	},
});
