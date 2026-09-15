# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_link_to_form


class ItemAlternative(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext.stock.doctype.item_alternative_bom.item_alternative_bom import ItemAlternativeBOM

		alternative_item_code: DF.Link | None
		alternative_item_name: DF.ReadOnly | None
		applicable_boms: DF.Table[ItemAlternativeBOM]
		item_code: DF.Link | None
		item_name: DF.ReadOnly | None
		restrict_to_boms: DF.Check
		two_way: DF.Check
	# end: auto-generated types

	def validate(self):
		self.has_alternative_item()
		self.validate_alternative_item()
		self.validate_duplicate()
		self.validate_bom_restriction()

	def has_alternative_item(self):
		if self.item_code and not frappe.db.get_value("Item", self.item_code, "allow_alternative_item"):
			frappe.throw(_("Cannot set alternative item for the item {0}").format(self.item_code))

	def validate_alternative_item(self):
		if self.item_code == self.alternative_item_code:
			frappe.throw(_("Alternative item must not be same as item code"))

		item_meta = frappe.get_meta("Item")
		fields = [
			"is_stock_item",
			"include_item_in_manufacturing",
			"has_serial_no",
			"has_batch_no",
			"allow_alternative_item",
		]
		item_data = frappe.db.get_value("Item", self.item_code, fields, as_dict=1)
		alternative_item_data = frappe.db.get_value("Item", self.alternative_item_code, fields, as_dict=1)

		for field in fields:
			if item_data.get(field) != alternative_item_data.get(field):
				raise_exception, alert = [1, False] if field == "is_stock_item" else [0, True]

				frappe.msgprint(
					_("The value of {0} differs between Items {1} and {2}").format(
						frappe.bold(item_meta.get_translated_label(field)),
						frappe.bold(self.alternative_item_code),
						frappe.bold(self.item_code),
					),
					alert=alert,
					raise_exception=raise_exception,
					indicator="Orange",
				)

		alternate_item_check_msg = _("Allow Alternative Item must be checked on Item {0}")

		if not item_data.allow_alternative_item:
			frappe.throw(alternate_item_check_msg.format(self.item_code))
		if self.two_way and not alternative_item_data.allow_alternative_item:
			frappe.throw(alternate_item_check_msg.format(self.alternative_item_code))

	def validate_duplicate(self):
		if frappe.db.get_value(
			"Item Alternative",
			{
				"item_code": self.item_code,
				"alternative_item_code": self.alternative_item_code,
				"name": ("!=", self.name),
			},
		):
			frappe.throw(_("Record already exists for the item {0}").format(self.item_code))

	def validate_bom_restriction(self):
		if not self.restrict_to_boms:
			self.applicable_boms = []
			return

		if not self.applicable_boms:
			frappe.throw(
				_("Applicable BOMs is required when Restrict to BOMs is checked"),
				frappe.MandatoryError,
			)

		seen = set()
		for row in self.applicable_boms:
			if not row.bom:
				frappe.throw(_("BOM is required in row {0} of Applicable BOMs").format(row.idx))

			if row.bom in seen:
				frappe.throw(_("BOM {0} is duplicated in Applicable BOMs").format(frappe.bold(row.bom)))
			seen.add(row.bom)


def get_item_alternative_record(item_code: str, alternative_item_code: str) -> dict | None:
	"""Return the Item Alternative row for a forward or two-way reverse pair."""
	record = frappe.db.get_value(
		"Item Alternative",
		{"item_code": item_code, "alternative_item_code": alternative_item_code},
		["name", "restrict_to_boms"],
		as_dict=True,
	)
	if record:
		return record

	return frappe.db.get_value(
		"Item Alternative",
		{"item_code": alternative_item_code, "alternative_item_code": item_code, "two_way": 1},
		["name", "restrict_to_boms"],
		as_dict=True,
	)


def is_alternative_allowed(item_code: str, alternative_item_code: str, bom_no: str | None = None) -> bool:
	"""Return whether substituting alternative_item_code for item_code is allowed under bom_no.

	No matching Item Alternative record preserves current ERPNext behaviour (allowed).
	Unrestricted records are always allowed. Restricted records require bom_no to be listed.
	"""
	if not item_code or not alternative_item_code or item_code == alternative_item_code:
		return True

	record = get_item_alternative_record(item_code, alternative_item_code)
	if not record:
		return True

	if not cint(record.restrict_to_boms):
		return True

	if not bom_no:
		return False

	return bool(
		frappe.db.exists(
			"Item Alternative BOM",
			{"parent": record.name, "parenttype": "Item Alternative", "bom": bom_no},
		)
	)


def validate_alternative_item_for_bom(
	item_code: str, alternative_item_code: str, bom_no: str | None = None, row=None
):
	"""Throw if a restricted Item Alternative does not allow this BOM."""
	if is_alternative_allowed(item_code, alternative_item_code, bom_no):
		return

	record = get_item_alternative_record(item_code, alternative_item_code)
	msg = _("Item {0} is not an allowed alternative for {1} against BOM {2}.").format(
		frappe.bold(alternative_item_code),
		frappe.bold(item_code),
		frappe.bold(bom_no) if bom_no else frappe.bold(_("(not set)")),
	)
	if record:
		msg = f"{msg} {get_link_to_form('Item Alternative', record.name)}"
	if row is not None and getattr(row, "idx", None):
		msg = _("Row #{0}: {1}").format(row.idx, msg)

	frappe.throw(msg, title=_("Invalid Alternative Item"))


def _parents_with_bom(bom_no: str, parent_names: list[str]) -> set[str]:
	if not parent_names:
		return set()

	return set(
		frappe.get_all(
			"Item Alternative BOM",
			filters={
				"parent": ["in", parent_names],
				"parenttype": "Item Alternative",
				"bom": bom_no,
			},
			pluck="parent",
		)
	)


def _collect_alternatives(rows: list[dict], item_field: str, bom_no: str | None) -> list[str]:
	restricted_parents = [row.name for row in rows if cint(row.restrict_to_boms)]
	allowed_restricted = _parents_with_bom(bom_no, restricted_parents) if bom_no else set()

	alternatives = []
	for row in rows:
		if cint(row.restrict_to_boms):
			if row.name not in allowed_restricted:
				continue
		alternatives.append(row.get(item_field))
	return alternatives


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_alternative_items(doctype: Any, txt: str, searchfield: Any, start: int, page_len: int, filters: dict):
	item_code = filters.get("item_code")
	bom_no = filters.get("bom_no")
	search = f"%{txt}%"
	# each leg has distinct values (validate_duplicate), so start+page_len rows per leg suffice
	limit = cint(start) + cint(page_len)

	forward_filters = {"item_code": item_code, "alternative_item_code": ["like", search]}
	reverse_filters = {
		"alternative_item_code": item_code,
		"item_code": ["like", search],
		"two_way": 1,
	}

	# Without BOM context, only unrestricted alternatives are returned so restricted
	# pairs cannot leak into pickers that have no manufacturing BOM.
	if not bom_no:
		forward_filters["restrict_to_boms"] = 0
		reverse_filters["restrict_to_boms"] = 0

	forward = frappe.get_all(
		"Item Alternative",
		filters=forward_filters,
		fields=["name", "alternative_item_code", "restrict_to_boms"],
		limit=limit,
	)
	reverse = frappe.get_all(
		"Item Alternative",
		filters=reverse_filters,
		fields=["name", "item_code", "restrict_to_boms"],
		limit=limit,
	)

	alternatives = _collect_alternatives(forward, "alternative_item_code", bom_no)
	alternatives += _collect_alternatives(reverse, "item_code", bom_no)

	# union (dedupe, preserve order) + paginate
	unique_items = list(dict.fromkeys(alternatives))
	return [[item] for item in unique_items[start : start + page_len]]
