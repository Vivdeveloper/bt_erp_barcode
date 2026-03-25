// Copyright (c) 2026, BT ERP and contributors
// For license information, please see license.txt

function generate_barcodes(frm) {
	if (!frm.doc.items || !frm.doc.items.length) {
		frappe.msgprint(__("Please add items first."));
		return;
	}
	frappe.call({
		method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.generate_serial_numbers_for_items",
		args: {
			items: frm.doc.items.map((row) => ({
				item_code: row.item_code,
				idx: row.idx,
			})),
			production_plan: frm.doc.production_plan || "",
			posting_date: frm.doc.posting_date,
		},
		callback(r) {
			if (!r.exc && r.message && r.message.length) {
				frm.doc.items.forEach((row, i) => {
					frappe.model.set_value("BT Barcode Item", row.name, "serial_number", r.message[i] || "");
				});
				frm.refresh_field("items");
				frm.save();
			}
		},
	});
}

frappe.ui.form.on("BT Barcode Item", "generate_barcode", function (frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	if (!row.item_code) {
		frappe.msgprint(__("Please set Item Code first."));
		return;
	}
	frappe.call({
		method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.generate_serial_number_for_row",
		args: {
			item_code: row.item_code,
			idx: row.idx,
			production_plan: frm.doc.production_plan || "",
			posting_date: frm.doc.posting_date,
		},
		callback(r) {
			if (!r.exc && r.message) {
				frappe.model.set_value(cdt, cdn, "serial_number", r.message);
				frm.refresh_field("items");
				frm.save();
			}
		},
	});
});

frappe.ui.form.on("BT Barcode", {
	refresh(frm) {
		frm.add_custom_button(__("Generate Barcodes"), function () {
			generate_barcodes(frm);
		}, __("Tools"));
	},
	production_plan(frm) {
		if (frm.doc.production_plan) {
			frappe.call({
				method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.get_items_from_production_plan",
				args: {
					production_plan: frm.doc.production_plan,
					posting_date: frm.doc.posting_date,
				},
				callback(r) {
					if (r.message && r.message.length) {
						frm.clear_table("items");
						r.message.forEach((row) => {
							frm.add_child("items", {
								item_code: row.item_code,
								item_name: row.item_name,
								qty: row.qty,
								uom: row.uom,
								serial_number: row.serial_number,
							});
						});
						frm.refresh_field("items");
					}
				},
			});
		} else {
			frm.clear_table("items");
			frm.refresh_field("items");
		}
	},
});

frappe.ui.form.on('BT Barcode Item', {
    generate_barcode: function(frm, cdt, cdn) {
        frappe.call({
            method: "bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode.generate_barcode",
            args: {
                production_plan: frm.doc.production_plan,
                posting_date: frm.doc.posting_date
            },
            callback: function(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, 'serial_number', r.message);
                    frappe.model.set_value(cdt, cdn, 'barcode', r.message);
                }
            }
        });
    }
});