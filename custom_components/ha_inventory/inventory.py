from __future__ import annotations

import os
import mimetypes
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict, Union

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Attachment:
    id: str
    category: str
    name: str
    content_type: str
    path: str
    uploaded_at: str


@dataclass
class Item:
    id: str
    name: str
    description: str = ""

    # Reuse HA built-ins
    area_id: Optional[str] = None          # area registry id
    zone_entity_id: Optional[str] = None   # zone.* entity id
    ha_label_ids: List[str] = field(default_factory=list)

    # HA Inventory categories (internal)
    category_id: Optional[str] = None

    quantity: float = 1.0
    unit: str = "pcs"

    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    purchase_currency: Optional[str] = None
    warranty_expires_at: Optional[str] = None

    serial_number: Optional[str] = None
    model_number: Optional[str] = None
    asset_tag: Optional[str] = None
    condition: Optional[str] = None
    archived: bool = False
    parent_item_id: Optional[str] = None

    custom_fields: Dict[str, Any] = field(default_factory=dict)
    attachments: List[Attachment] = field(default_factory=list)

    notes: str = ""

    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class Category:
    id: str
    name: str
    description: str = ""
    parent_id: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class _StoredData(TypedDict, total=False):
    items: List[Dict[str, Any]]
    categories: List[Dict[str, Any]]


class InventoryStore:
    """Persisted HA Inventory store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[_StoredData] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self.items: Dict[str, Item] = {}
        self.categories: Dict[str, Category] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        for raw_item in data.get("items", []):
            item_data = dict(raw_item)
            attachments = [Attachment(**a) for a in item_data.get("attachments", [])]
            item_data["attachments"] = attachments
            item = Item(**item_data)
            self.items[item.id] = item

        for raw_cat in data.get("categories", []):
            cat = Category(**raw_cat)
            self.categories[cat.id] = cat

    async def async_save(self) -> None:
        data: _StoredData = {
            "items": [],
            "categories": [],
        }

        for item in self.items.values():
            item_dict = asdict(item)
            item_dict["attachments"] = [asdict(a) for a in item.attachments]
            data["items"].append(item_dict)

        for cat in self.categories.values():
            data["categories"].append(asdict(cat))

        await self._store.async_save(data)

    #
    # Item CRUD
    #

    async def async_add_item(self, **data: Any) -> Item:
        item_id = data.get("id") or str(uuid.uuid4())
        data["id"] = item_id
        if "name" not in data:
            raise ValueError("Item name is required")

        if "attachments" in data:
            data.pop("attachments")

        item = Item(**data)
        self.items[item.id] = item
        await self.async_save()
        return item

    async def async_update_item(self, item_id: str, **changes: Any) -> Optional[Item]:
        item = self.items.get(item_id)
        if not item:
            return None

        for key, value in changes.items():
            if not hasattr(item, key):
                continue
            if key == "attachments":
                continue
            setattr(item, key, value)

        item.updated_at = _now_iso()
        await self.async_save()
        return item

    async def async_delete_item(self, item_id: str) -> bool:
        if item_id not in self.items:
            return False
        self.items.pop(item_id)
        await self.async_save()
        return True

    async def async_move_item_area(self, item_id: str, area_id: Optional[str]) -> Optional[Item]:
        item = self.items.get(item_id)
        if not item:
            return None
        item.area_id = area_id
        item.updated_at = _now_iso()
        await self.async_save()
        return item

    async def async_set_item_zone(self, item_id: str, zone_entity_id: Optional[str]) -> Optional[Item]:
        item = self.items.get(item_id)
        if not item:
            return None
        item.zone_entity_id = zone_entity_id
        item.updated_at = _now_iso()
        await self.async_save()
        return item

    #
    # Photo handling
    #

    def _ensure_photo_dir(self) -> str:
        photo_dir = self._hass.config.path("www/ha_inventory")
        os.makedirs(photo_dir, exist_ok=True)
        return photo_dir

    async def async_add_item_photo_from_bytes(
        self,
        item_id: str,
        content: bytes,
        *,
        suggested_filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Optional[Item]:
        item = self.items.get(item_id)
        if not item:
            return None

        photo_dir = self._ensure_photo_dir()

        if not mime_type:
            mime_type = "image/jpeg"

        ext = mimetypes.guess_extension(mime_type.split(";", 1)[0]) or ".jpg"

        if suggested_filename and "." in suggested_filename:
            ext = os.path.splitext(suggested_filename)[1] or ext

        filename = suggested_filename or f"{item_id}-{uuid.uuid4().hex}{ext}"
        filename = filename.replace("/", "_").replace("\\", "_")

        file_path = os.path.join(photo_dir, filename)
        with open(file_path, "wb") as f:
            f.write(content)

        attachment = Attachment(
            id=str(uuid.uuid4()),
            category="photo",
            name=filename,
            content_type=mime_type,
            path=f"/local/ha_inventory/{filename}",
            uploaded_at=_now_iso(),
        )

        item.attachments.append(attachment)
        item.updated_at = _now_iso()
        await self.async_save()
        return item

    async def async_add_item_photo_from_url(
        self,
        item_id: str,
        image_url: str,
        *,
        suggested_filename: Optional[str] = None,
    ) -> Optional[Item]:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        item = self.items.get(item_id)
        if not item:
            return None

        session = async_get_clientsession(self._hass)
        async with session.get(image_url) as resp:
            if resp.status != 200:
                return None
            content = await resp.read()
            mime_type = resp.headers.get("Content-Type", "image/jpeg")

        return await self.async_add_item_photo_from_bytes(
            item_id=item_id,
            content=content,
            suggested_filename=suggested_filename,
            mime_type=mime_type,
        )

    async def async_add_item_photo_from_file_info(
        self,
        item_id: str,
        file_info: Union[Dict[str, Any], Any],
    ) -> Optional[Item]:

        item = self.items.get(item_id)
        if not item:
            return None

        src_path = getattr(file_info, "path", None)
        filename = getattr(file_info, "filename", None)
        mime_type = getattr(file_info, "content_type", None)

        if not src_path and isinstance(file_info, dict):
            src_path = file_info.get("path")
            filename = file_info.get("filename", filename)
            mime_type = file_info.get("content_type", mime_type)

        if not src_path:
            return None

        try:
            with open(src_path, "rb") as f:
                content = f.read()
        except OSError:
            return None

        return await self.async_add_item_photo_from_bytes(
            item_id=item_id,
            content=content,
            suggested_filename=filename,
            mime_type=mime_type,
        )