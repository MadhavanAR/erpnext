// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Alternative", {
	setup: function (frm) {
		frm.fields_dict.item_code.get_query = () => {
			return {
				filters: {
					allow_alternative_item: 1,
				},
			};
		};

		frm.set_query("bom", "applicable_boms", () => {
			return {
				filters: {
					docstatus: 1,
					is_active: 1,
				},
			};
		});
	},

	restrict_to_boms: function (frm) {
		if (!frm.doc.restrict_to_boms) {
			frm.clear_table("applicable_boms");
			frm.refresh_field("applicable_boms");
		}
	},
});
