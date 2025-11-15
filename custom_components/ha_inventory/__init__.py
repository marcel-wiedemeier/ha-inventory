from __future__ import annotations

from typing import Any, Dict
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from .const import DOMAIN
from .inventory import InventoryStore


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up HA Inventory."""

    store = InventoryStore(hass)
    await store.async_load()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["store"] = store

    #
    # CRUD
    #

    async def handle_add_item(call: ServiceCall) -> None:
        await store.async_add_item(**call.data)

    async def handle_update_item(call: ServiceCall) -> None:
        item_id = call.data["id"]
        changes = dict(call.data)
        changes.pop("id", None)
        await store.async_update_item(item_id, **changes)

    async def handle_delete_item(call: ServiceCall) -> None:
        await store.async_delete_item(call.data["id"])

    async def handle_move_item_area(call: ServiceCall) -> None:
        await store.async_move_item_area(
            call.data["id"], call.data.get("area_id")
        )

    async def handle_set_item_zone(call: ServiceCall) -> None:
        await store.async_set_item_zone(
            call.data["id"], call.data.get("zone_entity_id")
        )

    #
    # Photo services
    #

    async def handle_add_item_photo_url(call: ServiceCall) -> None:
        await store.async_add_item_photo_from_url(
            call.data["id"],
            call.data["image_url"],
            suggested_filename=call.data.get("filename"),
        )

    async def handle_add_item_photo_upload(call: ServiceCall) -> None:
        await store.async_add_item_photo_from_file_info(
            call.data["id"],
            call.data["file"],
        )

    #
    # Register
    #

    hass.services.async_register(DOMAIN, "add_item", handle_add_item)
    hass.services.async_register(DOMAIN, "update_item", handle_update_item)
    hass.services.async_register(DOMAIN, "delete_item", handle_delete_item)
    hass.services.async_register(DOMAIN, "move_item_area", handle_move_item_area)
    hass.services.async_register(DOMAIN, "set_item_zone", handle_set_item_zone)

    hass.services.async_register(DOMAIN, "add_item_photo_url", handle_add_item_photo_url)
    hass.services.async_register(DOMAIN, "add_item_photo_upload", handle_add_item_photo_upload)

    return True