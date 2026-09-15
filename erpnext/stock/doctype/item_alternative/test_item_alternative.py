# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.utils import cint, flt, random_string

from erpnext.controllers.subcontracting_controller import make_rm_stock_entry
from erpnext.controllers.tests.test_subcontracting_controller import (
	get_subcontracting_order,
	make_service_item,
	set_backflush_based_on,
)
from erpnext.manufacturing.doctype.production_plan.test_production_plan import make_bom
from erpnext.manufacturing.doctype.work_order.mapper import make_stock_entry
from erpnext.manufacturing.doctype.work_order.test_work_order import make_wo_order_test_record
from erpnext.stock.doctype.item.test_item import create_item
from erpnext.stock.doctype.item_alternative.item_alternative import (
	get_alternative_items,
	is_alternative_allowed,
	validate_alternative_item_for_bom,
)
from erpnext.stock.doctype.stock_entry.services.manufacturing import get_alternative_finished_goods
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import (
	EmptyStockReconciliationItemsError,
)
from erpnext.stock.doctype.stock_reconciliation.test_stock_reconciliation import (
	create_stock_reconciliation,
)
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
	make_subcontracting_receipt,
)
from erpnext.tests.utils import ERPNextTestSuite


class TestItemAlternative(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		make_items()

	def test_alternative_item_for_subcontract_rm(self):
		set_backflush_based_on("BOM")

		create_stock_reconciliation(
			item_code="Alternate Item For A RW 1", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)
		create_stock_reconciliation(
			item_code="Test FG A RW 2", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)

		supplier_warehouse = "Test Supplier Warehouse - _TC"

		make_service_item("Subcontracted Service Item 1")
		service_items = [
			{
				"warehouse": "_Test Warehouse - _TC",
				"item_code": "Subcontracted Service Item 1",
				"qty": 5,
				"rate": 3000,
				"fg_item": "Test Finished Goods - A",
				"fg_item_qty": 5,
			},
		]
		sco = get_subcontracting_order(service_items=service_items, supplier_warehouse=supplier_warehouse)
		rm_items = [
			{
				"item_code": "Test Finished Goods - A",
				"rm_item_code": "Test FG A RW 1",
				"item_name": "Test FG A RW 1",
				"qty": 5,
				"warehouse": "_Test Warehouse - _TC",
				"rate": 2000,
				"amount": 10000,
				"stock_uom": "Nos",
			},
			{
				"item_code": "Test Finished Goods - A",
				"rm_item_code": "Test FG A RW 2",
				"item_name": "Test FG A RW 2",
				"qty": 5,
				"warehouse": "_Test Warehouse - _TC",
				"rate": 2000,
				"amount": 10000,
				"stock_uom": "Nos",
			},
		]

		reserved_qty_for_sub_contract = frappe.db.get_value(
			"Bin",
			{"item_code": "Test FG A RW 1", "warehouse": "_Test Warehouse - _TC"},
			"reserved_qty_for_sub_contract",
		)

		se = frappe.get_doc(make_rm_stock_entry(sco.name, rm_items))
		se.to_warehouse = supplier_warehouse
		se.insert()

		doc = frappe.get_doc("Stock Entry", se.name)
		for item in doc.items:
			if item.item_code == "Test FG A RW 1":
				item.item_code = "Alternate Item For A RW 1"
				item.item_name = "Alternate Item For A RW 1"
				item.description = "Alternate Item For A RW 1"
				item.original_item = "Test FG A RW 1"

		doc.save()
		doc.submit()
		after_transfer_reserved_qty_for_sub_contract = frappe.db.get_value(
			"Bin",
			{"item_code": "Test FG A RW 1", "warehouse": "_Test Warehouse - _TC"},
			"reserved_qty_for_sub_contract",
		)

		self.assertEqual(after_transfer_reserved_qty_for_sub_contract, flt(reserved_qty_for_sub_contract - 5))

		scr = make_subcontracting_receipt(sco.name)
		scr.save()

		scr = frappe.get_doc("Subcontracting Receipt", scr.name)
		status = False
		for item in scr.supplied_items:
			if item.rm_item_code == "Alternate Item For A RW 1":
				status = True

		self.assertEqual(status, True)
		set_backflush_based_on("Material Transferred for Subcontract")

	def test_alternative_item_for_production_rm(self):
		create_stock_reconciliation(
			item_code="Alternate Item For A RW 1", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)
		create_stock_reconciliation(
			item_code="Test FG A RW 2", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)
		pro_order = make_wo_order_test_record(
			production_item="Test Finished Goods - A",
			qty=5,
			source_warehouse="_Test Warehouse - _TC",
			wip_warehouse="Test Supplier Warehouse - _TC",
		)

		reserved_qty_for_production = frappe.db.get_value(
			"Bin",
			{"item_code": "Test FG A RW 1", "warehouse": "_Test Warehouse - _TC"},
			"reserved_qty_for_production",
		)

		ste = frappe.get_doc(make_stock_entry(pro_order.name, "Material Transfer for Manufacture", 5))
		ste.insert()

		for item in ste.items:
			if item.item_code == "Test FG A RW 1":
				item.item_code = "Alternate Item For A RW 1"
				item.item_name = "Alternate Item For A RW 1"
				item.description = "Alternate Item For A RW 1"
				item.original_item = "Test FG A RW 1"

		ste.submit()
		reserved_qty_for_production_after_transfer = frappe.db.get_value(
			"Bin",
			{"item_code": "Test FG A RW 1", "warehouse": "_Test Warehouse - _TC"},
			"reserved_qty_for_production",
		)

		self.assertEqual(reserved_qty_for_production_after_transfer, flt(reserved_qty_for_production - 5))
		ste1 = frappe.get_doc(make_stock_entry(pro_order.name, "Manufacture", 5))

		status = False
		for d in ste1.items:
			if d.item_code == "Alternate Item For A RW 1":
				status = True

		self.assertEqual(status, True)
		ste1.submit()

	def test_get_used_alternative_items_returns_substitution(self):
		# get_used_alternative_items (raw SQL -> frappe.qb) returns the alternative items substituted
		# into a work order's transfer entries, keyed by the original item. Exercises the converted
		# query on both engines.
		from erpnext.stock.doctype.stock_entry.stock_entry import get_used_alternative_items

		create_stock_reconciliation(
			item_code="Alternate Item For A RW 1", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)
		create_stock_reconciliation(
			item_code="Test FG A RW 2", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)
		pro_order = make_wo_order_test_record(
			production_item="Test Finished Goods - A",
			qty=5,
			source_warehouse="_Test Warehouse - _TC",
			wip_warehouse="Test Supplier Warehouse - _TC",
		)

		ste = frappe.get_doc(make_stock_entry(pro_order.name, "Material Transfer for Manufacture", 5))
		ste.insert()
		for item in ste.items:
			if item.item_code == "Test FG A RW 1":
				item.item_code = "Alternate Item For A RW 1"
				item.item_name = "Alternate Item For A RW 1"
				item.description = "Alternate Item For A RW 1"
				item.original_item = "Test FG A RW 1"
		ste.submit()

		used = get_used_alternative_items(work_order=pro_order.name)
		self.assertIn("Test FG A RW 1", used)
		self.assertEqual(used["Test FG A RW 1"].item_code, "Alternate Item For A RW 1")

	def test_get_used_alternative_items_for_subcontract_order(self):
		# Covers the subcontract_order branch of get_used_alternative_items (including the dynamic
		# subcontract_order_field column) on both engines.
		from erpnext.stock.doctype.stock_entry.stock_entry import get_used_alternative_items

		set_backflush_based_on("BOM")
		create_stock_reconciliation(
			item_code="Alternate Item For A RW 1", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)
		create_stock_reconciliation(
			item_code="Test FG A RW 2", warehouse="_Test Warehouse - _TC", qty=5, rate=2000
		)
		supplier_warehouse = "Test Supplier Warehouse - _TC"
		make_service_item("Subcontracted Service Item 1")
		service_items = [
			{
				"warehouse": "_Test Warehouse - _TC",
				"item_code": "Subcontracted Service Item 1",
				"qty": 5,
				"rate": 3000,
				"fg_item": "Test Finished Goods - A",
				"fg_item_qty": 5,
			},
		]
		sco = get_subcontracting_order(service_items=service_items, supplier_warehouse=supplier_warehouse)
		rm_items = [
			{
				"item_code": "Test Finished Goods - A",
				"rm_item_code": "Test FG A RW 1",
				"item_name": "Test FG A RW 1",
				"qty": 5,
				"warehouse": "_Test Warehouse - _TC",
				"rate": 2000,
				"amount": 10000,
				"stock_uom": "Nos",
			},
			{
				"item_code": "Test Finished Goods - A",
				"rm_item_code": "Test FG A RW 2",
				"item_name": "Test FG A RW 2",
				"qty": 5,
				"warehouse": "_Test Warehouse - _TC",
				"rate": 2000,
				"amount": 10000,
				"stock_uom": "Nos",
			},
		]

		se = frappe.get_doc(make_rm_stock_entry(sco.name, rm_items))
		se.to_warehouse = supplier_warehouse
		se.insert()
		for item in se.items:
			if item.item_code == "Test FG A RW 1":
				item.item_code = "Alternate Item For A RW 1"
				item.item_name = "Alternate Item For A RW 1"
				item.description = "Alternate Item For A RW 1"
				item.original_item = "Test FG A RW 1"
		se.save()
		se.submit()

		used = get_used_alternative_items(
			subcontract_order=sco.name, subcontract_order_field="subcontracting_order"
		)
		self.assertIn("Test FG A RW 1", used)
		self.assertEqual(used["Test FG A RW 1"].item_code, "Alternate Item For A RW 1")
		set_backflush_based_on("Material Transferred for Subcontract")

	def test_get_alternative_items_both_directions_and_dedup(self):
		"""get_alternative_items must return forward alternatives, reverse-only
		two_way alternatives, exclude one-way reverse rows, and dedupe an item
		that matches in both the forward and reverse legs of the old UNION."""
		suffix = random_string(8)
		base = f"_Test IA Base {suffix}"
		alt_fwd = f"_Test IA Fwd {suffix}"  # forward only (two_way=0)
		alt_both = f"_Test IA Both {suffix}"  # forward (two_way=1)
		alt_rev = f"_Test IA Rev {suffix}"  # reverse via two_way=1
		alt_norev = f"_Test IA NoRev {suffix}"  # reverse but two_way=0 -> excluded
		dup = f"_Test IA Dup {suffix}"  # forward AND reverse -> must dedupe

		for item_code in (base, alt_fwd, alt_both, alt_rev, alt_norev, dup):
			create_item(item_code)
			item = frappe.get_doc("Item", item_code)
			if not item.allow_alternative_item:
				item.allow_alternative_item = 1
				item.save()

		# forward rows: item_code = base
		make_item_alternative(base, alt_fwd, two_way=0)
		make_item_alternative(base, alt_both, two_way=1)
		make_item_alternative(base, dup, two_way=1)

		# reverse rows: alternative_item_code = base
		make_item_alternative(alt_rev, base, two_way=1)
		make_item_alternative(alt_norev, base, two_way=0)
		make_item_alternative(dup, base, two_way=1)

		# txt = the shared suffix so the LIKE matches every alternate but not `base`
		results = get_alternative_items("Item", suffix, "name", 0, 20, {"item_code": base})

		# structure: list of single-element lists
		self.assertTrue(all(isinstance(row, list) and len(row) == 1 for row in results))

		returned = [row[0] for row in results]

		# forward alternatives (both one-way and two_way) are returned
		self.assertIn(alt_fwd, returned)
		self.assertIn(alt_both, returned)

		# reverse alternative is only returned when the row is two_way
		self.assertIn(alt_rev, returned)
		self.assertNotIn(alt_norev, returned)

		# `base` itself is never an alternative of itself
		self.assertNotIn(base, returned)

		# an item matching both legs of the old UNION is deduped to a single row
		self.assertIn(dup, returned)
		self.assertEqual(returned.count(dup), 1)

	def test_get_alternative_items_respects_txt_filter(self):
		"""The txt LIKE filter must actually narrow the result set so a
		non-matching alternate is excluded (guards against a broken WHERE)."""
		suffix = random_string(8)
		base = f"_Test IA Filter Base {suffix}"
		matching = f"_Test IA Match {suffix}"
		other = f"_Test IA Other {suffix}"

		for item_code in (base, matching, other):
			create_item(item_code)
			item = frappe.get_doc("Item", item_code)
			if not item.allow_alternative_item:
				item.allow_alternative_item = 1
				item.save()

		make_item_alternative(base, matching, two_way=0)
		make_item_alternative(base, other, two_way=0)

		# search only for the `Match` alternate
		results = get_alternative_items("Item", f"Match {suffix}", "name", 0, 20, {"item_code": base})
		returned = [row[0] for row in results]

		self.assertIn(matching, returned)
		self.assertNotIn(other, returned)

	def test_get_alternative_items_case_insensitive_match(self):
		"""The txt match must stay case-insensitive on BOTH engines: MariaDB LIKE is
		case-insensitive by default, and frappe compiles the `like` filter to ILIKE on
		Postgres. A case-shifted search must still find an alternate whose stored code
		differs in case — this guards against the conversion degrading to a case-sensitive
		match (plain LIKE / ==) that would silently return nothing on Postgres."""
		suffix = random_string(8)
		base = f"_Test IA Case Base {suffix}"
		# distinctive mixed-case token in the stored alternate's code
		alt = f"_Test IA CaseToken AbCdE {suffix}"

		for item_code in (base, alt):
			create_item(item_code)
			item = frappe.get_doc("Item", item_code)
			if not item.allow_alternative_item:
				item.allow_alternative_item = 1
				item.save()

		make_item_alternative(base, alt, two_way=0)

		# search the LOWERCASED token ("abcde") against the stored "AbCdE"
		results = get_alternative_items(
			"Item", f"casetoken abcde {suffix}", "name", 0, 20, {"item_code": base}
		)
		returned = [row[0] for row in results]

		self.assertIn(alt, returned)

	def test_get_alternative_items_pagination(self):
		"""start/page_len must slice the deduped, order-preserving result."""
		suffix = random_string(8)
		base = f"_Test IA Page Base {suffix}"
		alts = [f"_Test IA Page {i} {suffix}" for i in range(3)]

		create_item(base)
		base_item = frappe.get_doc("Item", base)
		if not base_item.allow_alternative_item:
			base_item.allow_alternative_item = 1
			base_item.save()

		for alt in alts:
			create_item(alt)
			alt_item = frappe.get_doc("Item", alt)
			if not alt_item.allow_alternative_item:
				alt_item.allow_alternative_item = 1
				alt_item.save()
			make_item_alternative(base, alt, two_way=0)

		full = [row[0] for row in get_alternative_items("Item", suffix, "name", 0, 20, {"item_code": base})]
		self.assertEqual(len(full), 3)

		page = [row[0] for row in get_alternative_items("Item", suffix, "name", 1, 1, {"item_code": base})]
		self.assertEqual(len(page), 1)
		self.assertEqual(page[0], full[1])

	def test_get_alternative_items_pagination_is_bounded_and_exact(self):
		"""Each get_all is bounded to start+page_len rows, so the DB round trip stays small
		instead of fetching every alternative per keystroke. Walking the result in small pages
		must still reconstruct the complete deduped set — including an alternate that appears in
		BOTH legs (forward + reverse two_way) — with no item dropped or duplicated by the bound."""
		suffix = random_string(8)
		base = f"_Test IA Bound Base {suffix}"
		forwards = [f"_Test IA Bound Fwd {i} {suffix}" for i in range(3)]
		reverses = [f"_Test IA Bound Rev {i} {suffix}" for i in range(3)]
		dup = f"_Test IA Bound Dup {suffix}"  # forward AND reverse two_way -> deduped across legs

		for item_code in [base, dup, *forwards, *reverses]:
			create_item(item_code)
			item = frappe.get_doc("Item", item_code)
			if not item.allow_alternative_item:
				item.allow_alternative_item = 1
				item.save()

		for fwd in forwards:
			make_item_alternative(base, fwd, two_way=0)
		make_item_alternative(base, dup, two_way=1)  # dup via the forward leg
		for rev in reverses:
			make_item_alternative(rev, base, two_way=1)
		make_item_alternative(dup, base, two_way=1)  # dup also via the reverse leg

		full = [row[0] for row in get_alternative_items("Item", suffix, "name", 0, 50, {"item_code": base})]
		# 3 forward + 3 reverse + the single deduped dup = 7 distinct
		self.assertEqual(len(full), 7)
		self.assertEqual(full.count(dup), 1)

		# walk in pages of 2; bounded fetches must yield exactly the same set, once each
		collected = []
		for start in range(0, 8, 2):
			collected += [
				row[0] for row in get_alternative_items("Item", suffix, "name", start, 2, {"item_code": base})
			]

		self.assertEqual(len(collected), len(set(collected)))  # no duplicates introduced by paging
		self.assertEqual(set(collected), set(full))  # nothing dropped by the per-leg limit
		self.assertEqual(collected.count(dup), 1)  # the cross-leg dup survives exactly once

	def test_unrestricted_alternative_remains_global(self):
		"""Unrestricted A → B stays available with or without BOM context."""
		items, bom_x, _bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(items.source, items.alt_b, two_way=0)

		without_bom = _alt_codes(items.source)
		with_bom_x = _alt_codes(items.source, bom_x)
		with_bom_y = _alt_codes(items.source, _bom_y)

		self.assertIn(items.alt_b, without_bom)
		self.assertIn(items.alt_b, with_bom_x)
		self.assertIn(items.alt_b, with_bom_y)
		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, bom_x))
		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, _bom_y))
		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, None))

	def test_restricted_alternative_allowed_for_matching_bom(self):
		items, bom_x, _bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=1, applicable_boms=[bom_x]
		)

		self.assertIn(items.alt_b, _alt_codes(items.source, bom_x))
		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, bom_x))

	def test_restricted_alternative_hidden_for_wrong_bom(self):
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=1, applicable_boms=[bom_x]
		)

		self.assertNotIn(items.alt_b, _alt_codes(items.source, bom_y))
		self.assertNotIn(items.alt_b, _alt_codes(items.source))
		self.assertFalse(is_alternative_allowed(items.source, items.alt_b, bom_y))
		self.assertFalse(is_alternative_allowed(items.source, items.alt_b, None))

	def test_server_rejects_restricted_alternative_on_wrong_bom(self):
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=1, applicable_boms=[bom_x]
		)

		self.assertRaises(
			frappe.ValidationError,
			validate_alternative_item_for_bom,
			items.source,
			items.alt_b,
			bom_y,
		)
		# Matching BOM remains allowed
		validate_alternative_item_for_bom(items.source, items.alt_b, bom_x)

	def test_different_alternatives_per_bom(self):
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=1, applicable_boms=[bom_x]
		)
		make_item_alternative(
			items.source, items.alt_c, two_way=0, restrict_to_boms=1, applicable_boms=[bom_y]
		)

		alts_x = _alt_codes(items.source, bom_x)
		alts_y = _alt_codes(items.source, bom_y)

		self.assertIn(items.alt_b, alts_x)
		self.assertNotIn(items.alt_c, alts_x)
		self.assertIn(items.alt_c, alts_y)
		self.assertNotIn(items.alt_b, alts_y)

	def test_restricted_alternative_with_multiple_boms(self):
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source,
			items.alt_b,
			two_way=0,
			restrict_to_boms=1,
			applicable_boms=[bom_x, bom_y],
		)

		self.assertIn(items.alt_b, _alt_codes(items.source, bom_x))
		self.assertIn(items.alt_b, _alt_codes(items.source, bom_y))
		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, bom_x))
		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, bom_y))

	def test_restrict_to_boms_disabled_is_global(self):
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=0, applicable_boms=[bom_x]
		)

		# Master clears applicable_boms when restrict is off
		doc = frappe.get_doc(
			"Item Alternative", {"item_code": items.source, "alternative_item_code": items.alt_b}
		)
		self.assertEqual(doc.restrict_to_boms, 0)
		self.assertEqual(len(doc.applicable_boms), 0)

		self.assertIn(items.alt_b, _alt_codes(items.source))
		self.assertIn(items.alt_b, _alt_codes(items.source, bom_y))

	def test_existing_unrestricted_records_unchanged(self):
		"""Legacy-style Item Alternative without restriction fields behaves globally."""
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		doc = make_item_alternative(items.source, items.alt_b, two_way=0)
		self.assertEqual(cint(doc.restrict_to_boms), 0)
		self.assertEqual(doc.applicable_boms, [])

		self.assertIn(items.alt_b, _alt_codes(items.source))
		self.assertIn(items.alt_b, _alt_codes(items.source, bom_x))
		self.assertIn(items.alt_b, _alt_codes(items.source, bom_y))

	def test_two_way_inherits_bom_restriction(self):
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=1, restrict_to_boms=1, applicable_boms=[bom_x]
		)

		# Reverse lookup B → A on matching BOM
		self.assertIn(items.source, _alt_codes(items.alt_b, bom_x))
		self.assertTrue(is_alternative_allowed(items.alt_b, items.source, bom_x))

		# Reverse lookup on wrong BOM / without BOM context
		self.assertNotIn(items.source, _alt_codes(items.alt_b, bom_y))
		self.assertNotIn(items.source, _alt_codes(items.alt_b))
		self.assertFalse(is_alternative_allowed(items.alt_b, items.source, bom_y))

	def test_unregistered_substitution_still_allowed(self):
		"""No Item Alternative record → substitution remains allowed (existing behaviour)."""
		items, bom_x, _bom_y = self._make_bom_restriction_fixture()

		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, bom_x))
		self.assertTrue(is_alternative_allowed(items.source, items.alt_b, None))
		validate_alternative_item_for_bom(items.source, items.alt_b, bom_x)

	def test_stock_entry_rejects_restricted_alternative_bypass(self):
		"""API/direct Stock Entry with a wrong-BOM restricted alternative must fail validation."""
		items, bom_x, bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=1, applicable_boms=[bom_x]
		)

		warehouse = "_Test Warehouse - _TC"
		create_stock_reconciliation(item_code=items.alt_b, warehouse=warehouse, qty=10, rate=100)

		wo = make_wo_order_test_record(
			production_item=items.fg_y,
			bom_no=bom_y,
			qty=1,
			source_warehouse=warehouse,
			wip_warehouse=warehouse,
			fg_warehouse=warehouse,
			skip_transfer=1,
		)

		ste = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", 1))
		ste.insert()

		# Bypass the Alternate Item picker: force a restricted alternative for the wrong BOM
		rm_row = next(d for d in ste.items if d.item_code == items.source)
		rm_row.item_code = items.alt_b
		rm_row.original_item = items.source

		self.assertRaises(frappe.ValidationError, ste.save)

		# Matching BOM still accepts the same substitution
		wo_ok = make_wo_order_test_record(
			production_item=items.fg_x,
			bom_no=bom_x,
			qty=1,
			source_warehouse=warehouse,
			wip_warehouse=warehouse,
			fg_warehouse=warehouse,
			skip_transfer=1,
		)
		ste_ok = frappe.get_doc(make_stock_entry(wo_ok.name, "Manufacture", 1))
		ste_ok.insert()
		rm_ok = next(d for d in ste_ok.items if d.item_code == items.source)
		rm_ok.item_code = items.alt_b
		rm_ok.original_item = items.source
		ste_ok.save()
		self.assertEqual(rm_ok.item_code, items.alt_b)
		self.assertEqual(rm_ok.original_item, items.source)

	def test_restricted_alternative_rejected_without_bom_context(self):
		"""Restricted alternatives must not slip through BOM-less manufacturing entries."""
		items, bom_x, _bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=1, applicable_boms=[bom_x]
		)

		warehouse = "_Test Warehouse - _TC"
		create_stock_reconciliation(item_code=items.alt_b, warehouse=warehouse, qty=5, rate=100)
		create_stock_reconciliation(item_code=items.rm2, warehouse=warehouse, qty=5, rate=100)

		ste = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Manufacture",
				"purpose": "Manufacture",
				"company": "_Test Company",
				"fg_completed_qty": 1,
				"items": [
					{
						"item_code": items.alt_b,
						"original_item": items.source,
						"qty": 1,
						"s_warehouse": warehouse,
						"allow_alternative_item": 1,
					},
					{
						"item_code": items.fg_x,
						"qty": 1,
						"t_warehouse": warehouse,
						"is_finished_item": 1,
					},
				],
			}
		)
		self.assertRaises(frappe.ValidationError, ste.insert)

	def test_allowed_transfer_preserves_original_item_on_manufacture(self):
		items, bom_x, _bom_y = self._make_bom_restriction_fixture()
		make_item_alternative(
			items.source, items.alt_b, two_way=0, restrict_to_boms=1, applicable_boms=[bom_x]
		)

		warehouse = "_Test Warehouse - _TC"
		wip = "Stores - _TC"
		create_stock_reconciliation(item_code=items.alt_b, warehouse=warehouse, qty=5, rate=100)
		create_stock_reconciliation(item_code=items.rm2, warehouse=warehouse, qty=5, rate=100)

		wo = make_wo_order_test_record(
			production_item=items.fg_x,
			bom_no=bom_x,
			qty=1,
			source_warehouse=warehouse,
			wip_warehouse=wip,
			fg_warehouse=warehouse,
		)

		transfer = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", 1))
		transfer.insert()
		for row in transfer.items:
			if row.item_code == items.source:
				row.item_code = items.alt_b
				row.original_item = items.source
		transfer.save()
		transfer.submit()

		manufacture = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", 1))
		manufacture.insert()

		rm_rows = [d for d in manufacture.items if d.s_warehouse]
		alt_row = next((d for d in rm_rows if d.item_code == items.alt_b), None)
		self.assertIsNotNone(alt_row)
		self.assertEqual(alt_row.original_item, items.source)

	def test_finished_goods_alternatives_ignore_bom_restriction(self):
		"""BOM restriction must not change get_alternative_finished_goods."""
		suffix = random_string(8)
		fg = f"_Test IA FG Conv {suffix}"
		alt_fg = f"_Test IA FG Alt {suffix}"
		dummy_rm = f"_Test IA FG RM {suffix}"

		for code in (fg, alt_fg, dummy_rm):
			create_item(code)
			item = frappe.get_doc("Item", code)
			item.allow_alternative_item = 1
			item.save()

		bom = make_bom(item=fg, raw_materials=[dummy_rm], company="_Test Company")
		# Restrict the FG→alt_fg pair to this BOM; finished-goods lookup must still return it
		# regardless of BOM context (API does not take a BOM).
		make_item_alternative(fg, alt_fg, two_way=0, restrict_to_boms=1, applicable_boms=[bom.name])

		alternatives = get_alternative_finished_goods(fg)
		self.assertIn(alt_fg, alternatives)

	def test_restrict_to_boms_requires_applicable_bom(self):
		items, _bom_x, _bom_y = self._make_bom_restriction_fixture()
		doc = frappe.get_doc(
			{
				"doctype": "Item Alternative",
				"item_code": items.source,
				"alternative_item_code": items.alt_b,
				"restrict_to_boms": 1,
			}
		)
		self.assertRaises(frappe.MandatoryError, doc.insert)

	def test_duplicate_applicable_bom_rejected(self):
		items, bom_x, _bom_y = self._make_bom_restriction_fixture()
		doc = frappe.get_doc(
			{
				"doctype": "Item Alternative",
				"item_code": items.source,
				"alternative_item_code": items.alt_b,
				"restrict_to_boms": 1,
				"applicable_boms": [{"bom": bom_x}, {"bom": bom_x}],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def _make_bom_restriction_fixture(self):
		suffix = random_string(8)
		items = frappe._dict(
			source=f"_Test IA Src {suffix}",
			alt_b=f"_Test IA AltB {suffix}",
			alt_c=f"_Test IA AltC {suffix}",
			rm2=f"_Test IA RM2 {suffix}",
			fg_x=f"_Test IA FGX {suffix}",
			fg_y=f"_Test IA FGY {suffix}",
		)
		for code in items.values():
			create_item(code)
			item = frappe.get_doc("Item", code)
			if not item.allow_alternative_item:
				item.allow_alternative_item = 1
				item.save()

		bom_x = make_bom(
			item=items.fg_x, raw_materials=[items.source, items.rm2], company="_Test Company"
		).name
		bom_y = make_bom(
			item=items.fg_y, raw_materials=[items.source, items.rm2], company="_Test Company"
		).name
		return items, bom_x, bom_y


def _alt_codes(item_code, bom_no=None):
	filters = {"item_code": item_code}
	if bom_no:
		filters["bom_no"] = bom_no
	return [row[0] for row in get_alternative_items("Item", "", "name", 0, 50, filters)]


def make_item_alternative(item_code, alternative_item_code, two_way=0, restrict_to_boms=0, applicable_boms=None):
	doc = frappe.get_doc(
		{
			"doctype": "Item Alternative",
			"item_code": item_code,
			"alternative_item_code": alternative_item_code,
			"two_way": two_way,
			"restrict_to_boms": restrict_to_boms,
		}
	)
	for bom in applicable_boms or []:
		doc.append("applicable_boms", {"bom": bom})
	doc.insert()
	return doc


def make_items():
	items = [
		"Test Finished Goods - A",
		"Test FG A RW 1",
		"Test FG A RW 2",
		"Alternate Item For A RW 1",
	]
	for item_code in items:
		if not frappe.db.exists("Item", item_code):
			create_item(item_code)

	try:
		create_stock_reconciliation(
			item_code="Test FG A RW 1", warehouse="_Test Warehouse - _TC", qty=10, rate=2000
		)
	except EmptyStockReconciliationItemsError:
		pass

	if frappe.db.exists("Item", "Test FG A RW 1"):
		doc = frappe.get_doc("Item", "Test FG A RW 1")
		doc.allow_alternative_item = 1
		doc.save()

	if frappe.db.exists("Item", "Test Finished Goods - A"):
		doc = frappe.get_doc("Item", "Test Finished Goods - A")
		doc.is_sub_contracted_item = 1
		doc.save()

	if not frappe.db.get_value("BOM", {"item": "Test Finished Goods - A", "docstatus": 1}):
		make_bom(item="Test Finished Goods - A", raw_materials=["Test FG A RW 1", "Test FG A RW 2"])

	if not frappe.db.get_value("Warehouse", {"warehouse_name": "Test Supplier Warehouse"}):
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "Test Supplier Warehouse",
				"company": "_Test Company",
			}
		).insert(ignore_permissions=True)
