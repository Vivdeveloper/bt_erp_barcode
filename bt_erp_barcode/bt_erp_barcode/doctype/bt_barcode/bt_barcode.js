// Copyright (c) 2026, BT ERP and contributors
// For license information, please see license.txt

const PRODUCTION_PLAN_FILTER = {
	filters: { docstatus: ["in", [0, 1]] },
};

function setup_order_acceptance_query(frm) {
	frm.set_query("order_acceptance", () => {
		const production_plan = (frm.doc.production_plan || "").trim();
		const names = frm._order_acceptances || [];

		if (!production_plan) {
			return { filters: { name: ["in", []] } };
		}

		return {
			filters: {
				docstatus: ["in", [0, 1]],
				name: ["in", names.length ? names : ["__none__"]],
			},
		};
	});
}

function refresh_order_acceptance_filter(frm) {
	const production_plan = (frm.doc.production_plan || "").trim();
	if (!production_plan) {
		frm._order_acceptances = [];
		return;
	}

	frappe.call({
		method:
			"bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.get_order_acceptances_for_production_plan",
		args: { production_plan },
		callback(r) {
			frm._order_acceptances = r.message || [];
		},
	});
}

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
	frappe.call({
		method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.generate_barcode",
		args: {
			item_code: row.item_code,
			idx: row.idx,
			production_plan: frm.doc.production_plan || "",
			posting_date: frm.doc.posting_date,
			existing_serials: JSON.stringify(get_other_serials(frm, cdn)),
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
			inject_grid_barcode_buttons(frm);
			return out;
		};
	}
}

function populate_production_plans(frm, plans) {
	frm.clear_table("production_plans");
	(plans || []).forEach((plan) => {
		frm.add_child("production_plans", { production_plan: plan });
	});
	frm.refresh_field("production_plans");
}

function fetch_production_plans(frm) {
	const production_plan = (frm.doc.production_plan || "").trim();
	if (!production_plan) {
		populate_production_plans(frm, []);
		refresh_order_acceptance_filter(frm);
		return;
	}
	frappe.call({
		method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.get_production_plans",
		args: { production_plan },
		callback(r) {
			if (r.exc || !r.message) {
				return;
			}
			const { base, plans } = r.message;
			if (base && base !== frm.doc.production_plan) {
				// frm.doc.production_plan = base;
				// frm.refresh_field("production_plan");
			}
			populate_production_plans(frm, plans);
			refresh_order_acceptance_filter(frm);
		},
	});
}

function populate_items(frm, items) {
	frm.clear_table("items");
	(items || []).forEach((row) => {
		const child = frm.add_child("items", {
			item_code: row.item_code,
			customer_ref_code: row.customer_ref_code || "",
			qty: row.qty,
			uom: row.uom,
			serial_number: row.serial_number || "",
		});
		if (row.item_name) {
			frappe.model.set_value(child.doctype, child.name, "item_name", row.item_name);
		}
	});
	frm.refresh_field("items");
	inject_grid_barcode_buttons(frm);
}

function fetch_items_from_order_acceptance(frm) {
	const order_acceptance = (frm.doc.order_acceptance || "").trim();
	const production_plan = (frm.doc.production_plan || "").trim();
	if (!order_acceptance) {
		populate_items(frm, []);
		return;
	}
	frappe.call({
		method:
			"bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.get_items_from_order_acceptance",
		args: {
			order_acceptance,
			production_plan,
		},
		callback(r) {
			if (!r.exc) {
				populate_items(frm, r.message || []);
			}
		},
	});
}

frappe.ui.form.on("BT Barcode", {
	refresh(frm) {
		inject_grid_barcode_buttons(frm);
		frm.set_query("production_plan", () => PRODUCTION_PLAN_FILTER);
		frm.set_query("production_plan", "production_plans", () => PRODUCTION_PLAN_FILTER);
		setup_order_acceptance_query(frm);
		refresh_order_acceptance_filter(frm);
	},
	production_plan(frm) {
		fetch_production_plans(frm);
		if (frm.doc.order_acceptance) {
			fetch_items_from_order_acceptance(frm);
		}
	},
	order_acceptance(frm) {
		fetch_items_from_order_acceptance(frm);
	},
});

frappe.ui.form.on("BT Barcode Item", {
	generate_barcode(frm, cdt, cdn) {
		bt_barcode_generate_row(frm, cdt, cdn);
	},
});
