"""Application wiring for the rumps toolbar unit converter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Final, NewType, Protocol, cast

import objc  # type: ignore[import-untyped]
import rumps
from AppKit import (  # type: ignore[import-untyped]
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezelBorder,
    NSEventMaskLeftMouseUp,
    NSEventMaskRightMouseUp,
    NSEventModifierFlagCommand,
    NSEventTypeRightMouseUp,
    NSImage,
    NSImageScaleProportionallyDown,
    NSMenu,
    NSMenuItem,
    NSPanel,
    NSScreen,
    NSScrollView,
    NSSplitView,
    NSSplitViewDividerStyleThin,
    NSStatusWindowLevel,
    NSTextView,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindowCollectionBehaviorMoveToActiveSpace,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSNotification, NSObject  # type: ignore[import-untyped]
from rumps import MenuItem, events  # type: ignore[import-untyped]

from .calculator import render_results

ObjCId = NewType("ObjCId", object)


class _Size(Protocol):
    width: float
    height: float


class _Rect(Protocol):
    size: _Size


@dataclass(frozen=True)
class PanelGeometry:
    """Describe the preferred and minimum panel sizes."""

    size: tuple[float, float]
    min_size: tuple[float, float]
    split_ratio: float
    min_ratio: float


PANEL_GEOMETRY: Final[PanelGeometry] = PanelGeometry(
    size=(460.0, 220.0),
    min_size=(320.0, 160.0),
    split_ratio=0.6,
    min_ratio=0.45,
)


_STATUS_ICON_RESOURCE: Final[str] = "ph_switch_mb_icon.svg"
_STATUS_ICON_SIZE: Final[tuple[float, float]] = (18.0, 18.0)


def _load_status_icon() -> NSImage | None:
    """Load the status-bar icon if the resource is available."""

    resource = resources.files(__package__).joinpath(_STATUS_ICON_RESOURCE)
    try:
        with resources.as_file(resource) as icon_path:
            image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
    except FileNotFoundError:
        return None

    if image is None:
        return None

    image.setTemplate_(False)
    image.setSize_(_STATUS_ICON_SIZE)
    return image


class _StatusButtonHandler(NSObject):
    """Objective-C bridge that reacts to status item clicks."""

    def initWithApp_(self, app: ToolbarApp) -> ObjCId | None:  # noqa: N802
        self = objc.super(_StatusButtonHandler, self).init()
        if self is None:
            return None
        self._app = app
        return self

    @objc.IBAction  # noqa: PYI017
    def togglePanel_(self, _sender: ObjCId) -> None:  # noqa: N802
        current_event = NSApplication.sharedApplication().currentEvent()
        if current_event is not None and current_event.type() == NSEventTypeRightMouseUp:
            self._app.show_context_menu()
            return
        self._app.toggle_panel()


class _ContextMenuHandler(NSObject):
    """Provides actions for the status-item context menu."""

    def initWithApp_(self, app: ToolbarApp) -> ObjCId | None:  # noqa: N802
        self = objc.super(_ContextMenuHandler, self).init()
        if self is None:
            return None
        self._app = app
        return self

    @objc.IBAction  # noqa: PYI017
    def quitApp_(self, _sender: ObjCId) -> None:  # noqa: N802
        self._app.quit_app()


class _TextChangeObserver(NSObject):
    """Tracks edits in the input text view and triggers updates."""

    def initWithApp_(self, app: ToolbarApp) -> ObjCId | None:  # noqa: N802
        self = objc.super(_TextChangeObserver, self).init()
        if self is None:
            return None
        self._app = app
        return self

    def textDidChange_(self, notification: ObjCId) -> None:  # noqa: N802
        ns_notification = cast(NSNotification, notification)
        text_view = cast(NSTextView, ns_notification.object())  # type: ignore[no-any-return]
        self._app.handle_text_change(text_view)


class _SplitViewDelegate(NSObject):
    """Constrains the split view so both panes remain visible."""

    def initWithRatios_(self, ratios: tuple[float, float]) -> ObjCId | None:  # noqa: N802
        self = objc.super(_SplitViewDelegate, self).init()
        if self is None:
            return None
        self._min_left, self._min_right = ratios
        return self

    def splitView_constrainMinCoordinate_ofSubviewAt_(  # noqa: N802
        self, split_view: NSSplitView, proposed_coordinate: float, divider_index: int
    ) -> float:
        if divider_index == 0:
            return max(proposed_coordinate, self._min_left)
        return proposed_coordinate

    def splitView_constrainMaxCoordinate_ofSubviewAt_(  # noqa: N802
        self, split_view: NSSplitView, proposed_coordinate: float, divider_index: int
    ) -> float:
        if divider_index == 0:
            total_width = split_view.bounds().size.width
            return min(proposed_coordinate, total_width - self._min_right)
        return proposed_coordinate

    def splitView_constrainSplitPosition_ofSubviewAt_(  # noqa: N802
        self, split_view: NSSplitView, proposed_position: float, divider_index: int
    ) -> float:
        if divider_index != 0:
            return proposed_position

        total_width = split_view.bounds().size.width
        min_position = self._min_left
        max_position = max(min_position, total_width - self._min_right)
        return min(max(proposed_position, min_position), max_position)


class ToolbarApp(rumps.App):
    """Status-bar app that toggles a free-form text panel."""

    def __init__(self) -> None:
        super().__init__("rumps-input", title="", quit_button=None)
        self.menu: list[MenuItem] = []
        self._text_view: NSTextView | None = None
        self._result_view: NSTextView | None = None
        self._panel_delegate = _StatusButtonHandler.alloc().initWithApp_(self)
        self._text_delegate = _TextChangeObserver.alloc().initWithApp_(self)
        self._split_delegate = _SplitViewDelegate.alloc().initWithRatios_(self._minimum_split_widths())
        self._context_menu_handler = _ContextMenuHandler.alloc().initWithApp_(self)
        self._panel = self._build_panel()
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self._ensure_edit_menu()
        self._ensure_window_menu()
        self._status_icon = _load_status_icon()
        self._context_menu = self._build_context_menu()
        events.before_start(self._configure_status_item)

    def _minimum_split_widths(self) -> tuple[float, float]:
        width, _ = PANEL_GEOMETRY.min_size
        target = width * PANEL_GEOMETRY.min_ratio
        return (target, target)

    def _build_panel(self) -> NSPanel:
        panel = _create_panel(PANEL_GEOMETRY)
        content_bounds = cast(_Rect, panel.contentView().bounds())
        split_view = _create_split_view(content_bounds, self._split_delegate)

        input_view = _create_input_view(content_bounds, self._text_delegate)
        result_view = _create_result_view(content_bounds, input_view)

        split_view.addSubview_(input_view.scroll)
        split_view.addSubview_(result_view.scroll)
        split_view.setHoldingPriority_forSubviewAtIndex_(260.0, 0)
        split_view.setHoldingPriority_forSubviewAtIndex_(250.0, 1)
        split_view.setPosition_ofDividerAtIndex_(
            0,
            content_bounds.size.width * PANEL_GEOMETRY.split_ratio,
        )
        split_view.adjustSubviews()
        if hasattr(split_view, "layoutSubtreeIfNeeded"):
            split_view.layoutSubtreeIfNeeded()
        split_view.setNeedsDisplay_(True)

        panel.setContentView_(split_view)
        panel.setInitialFirstResponder_(input_view.text)
        self._text_view = input_view.text
        self._result_view = result_view.text
        return panel

    def _ensure_edit_menu(self) -> None:
        ns_app = NSApplication.sharedApplication()
        main_menu = ns_app.mainMenu()
        if main_menu is None:
            main_menu = NSMenu.alloc().initWithTitle_("MainMenu")
            ns_app.setMainMenu_(main_menu)

        if main_menu.itemWithTitle_("Edit") is not None:
            return

        edit_menu = NSMenu.alloc().initWithTitle_("Edit")
        edit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Edit",
            None,
            "",
        )
        edit_item.setSubmenu_(edit_menu)

        def _add_menu_item(title: str, action: str, key: str) -> None:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title,
                action,
                key,
            )
            item.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
            edit_menu.addItem_(item)

        _add_menu_item("Cut", "cut:", "x")
        _add_menu_item("Copy", "copy:", "c")
        _add_menu_item("Paste", "paste:", "v")
        edit_menu.addItem_(NSMenuItem.separatorItem())
        _add_menu_item("Select All", "selectAll:", "a")

        main_menu.addItem_(edit_item)

    def _ensure_window_menu(self) -> None:
        ns_app = NSApplication.sharedApplication()
        main_menu = ns_app.mainMenu()
        if main_menu is None:
            return

        if main_menu.itemWithTitle_("Window") is not None:
            return

        window_menu = NSMenu.alloc().initWithTitle_("Window")
        window_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Window",
            None,
            "",
        )
        window_item.setSubmenu_(window_menu)

        close_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Close Window",
            "performClose:",
            "w",
        )
        close_item.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
        if self._panel is not None:
            close_item.setTarget_(self._panel)

        window_menu.addItem_(close_item)
        main_menu.addItem_(window_item)

    def _configure_status_item(self) -> None:
        status_item = self._nsapp.nsstatusitem
        status_item.setMenu_(None)
        status_item.setHighlightMode_(False)
        button = status_item.button()
        button.setTarget_(self._panel_delegate)
        button.setAction_("togglePanel:")
        button.sendActionOn_(NSEventMaskLeftMouseUp | NSEventMaskRightMouseUp)
        if self._status_icon is not None:
            button.setImage_(self._status_icon)
            if hasattr(button, "setImageScaling_"):
                button.setImageScaling_(NSImageScaleProportionallyDown)
            button.setTitle_("")
        else:
            button.setTitle_("TXT")

    def toggle_panel(self) -> None:
        if self._panel.isVisible():
            ns_app = NSApplication.sharedApplication()
            ns_app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            self._panel.orderOut_(None)
            return

        self._position_panel()
        ns_app = NSApplication.sharedApplication()
        ns_app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        ns_app.activateIgnoringOtherApps_(True)
        self._panel.makeKeyAndOrderFront_(None)
        if self._text_view is not None:
            self._panel.makeFirstResponder_(self._text_view)
            window = self._text_view.window()
            if window is not None:
                window.makeFirstResponder_(self._text_view)
        self._update_result_from_input()

    def _position_panel(self) -> None:
        status_item = self._nsapp.nsstatusitem
        button = status_item.button()
        button_window = button.window()
        rect_in_window = button.convertRect_toView_(button.bounds(), None)
        rect_on_screen = button_window.convertRectToScreen_(rect_in_window)

        panel_frame = self._panel.frame()
        screen = button_window.screen() or NSScreen.mainScreen()
        screen_frame = screen.visibleFrame()

        new_x = rect_on_screen.origin.x + (rect_on_screen.size.width - panel_frame.size.width) / 2.0
        min_x = screen_frame.origin.x
        max_x = screen_frame.origin.x + screen_frame.size.width - panel_frame.size.width
        new_x = max(min_x, min(new_x, max_x))

        new_y = rect_on_screen.origin.y - panel_frame.size.height
        min_y = screen_frame.origin.y
        new_y = max(new_y, min_y)

        self._panel.setFrameOrigin_((new_x, new_y))

    def handle_text_change(self, text_view: NSTextView) -> None:
        if text_view is not self._text_view:
            return
        self._update_result_from_input()

    def _update_result_from_input(self) -> None:
        if self._text_view is None or self._result_view is None:
            return

        lines = self._text_view.string().splitlines()
        outputs = render_results(lines)
        self._result_view.setString_("\n".join(outputs))

    def show_context_menu(self) -> None:
        if self._context_menu is None:
            return
        status_item = self._nsapp.nsstatusitem
        status_item.popUpStatusItemMenu_(self._context_menu)

    def quit_app(self) -> None:
        if self._panel.isVisible():
            self._panel.orderOut_(None)
        rumps.quit_application()

    def _build_context_menu(self) -> NSMenu | None:
        if self._context_menu_handler is None:
            return None

        menu = NSMenu.alloc().initWithTitle_("ContextMenu")
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit",
            "quitApp:",
            "",
        )
        quit_item.setTarget_(self._context_menu_handler)
        menu.addItem_(quit_item)
        return menu


@dataclass
class _TextViewBundle:
    """Holds a text view together with its scroll view."""

    text: NSTextView
    scroll: NSScrollView


def _create_panel(geometry: PanelGeometry) -> NSPanel:
    frame = NSMakeRect(0.0, 0.0, *geometry.size)
    style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        frame,
        style,
        NSBackingStoreBuffered,
        False,
    )
    panel.setTitle_("")
    panel.setReleasedWhenClosed_(False)
    panel.setHidesOnDeactivate_(False)
    panel.setLevel_(NSStatusWindowLevel)
    panel.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)
    panel.setBecomesKeyOnlyIfNeeded_(False)
    panel.setContentMinSize_(geometry.min_size)
    return panel


def _create_split_view(bounds: _Rect, delegate: _SplitViewDelegate) -> NSSplitView:
    split_view = NSSplitView.alloc().initWithFrame_(bounds)
    split_view.setVertical_(True)
    split_view.setDividerStyle_(NSSplitViewDividerStyleThin)
    split_view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    split_view.setDelegate_(delegate)
    return split_view


def _create_input_view(bounds: _Rect, delegate: _TextChangeObserver) -> _TextViewBundle:
    width = bounds.size.width * PANEL_GEOMETRY.split_ratio
    frame = cast(_Rect, NSMakeRect(0.0, 0.0, width, bounds.size.height))
    text_view = _build_text_view(frame, editable=True, delegate=delegate)
    scroll = _build_scroll_view(frame, text_view)
    return _TextViewBundle(text=text_view, scroll=scroll)


def _create_result_view(bounds: _Rect, input_bundle: _TextViewBundle) -> _TextViewBundle:
    width = bounds.size.width * (1.0 - PANEL_GEOMETRY.split_ratio)
    frame = cast(_Rect, NSMakeRect(0.0, 0.0, width, bounds.size.height))
    text_view = _build_text_view(frame, editable=False, delegate=None)
    if input_bundle.text.drawsBackground():
        text_view.setDrawsBackground_(True)
        text_view.setBackgroundColor_(input_bundle.text.backgroundColor())
    scroll = _build_scroll_view(frame, text_view)
    return _TextViewBundle(text=text_view, scroll=scroll)


def _build_text_view(
    frame: _Rect,
    *,
    editable: bool,
    delegate: _TextChangeObserver | None,
) -> NSTextView:
    text_view = NSTextView.alloc().initWithFrame_(frame)
    text_view.setRichText_(False)
    text_view.setUsesFindPanel_(True)
    text_view.setAutomaticQuoteSubstitutionEnabled_(False)
    text_view.setAutomaticDashSubstitutionEnabled_(False)
    text_view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    text_view.setHorizontallyResizable_(True)
    text_view.setVerticallyResizable_(True)
    text_view.setMinSize_((0.0, 0.0))
    text_view.setMaxSize_((float("inf"), float("inf")))
    text_view.setEditable_(editable)
    text_view.setSelectable_(True)
    if delegate is not None:
        text_view.setDelegate_(delegate)
    return text_view


def _build_scroll_view(frame: _Rect, document_view: NSTextView) -> NSScrollView:
    scroll = NSScrollView.alloc().initWithFrame_(frame)
    scroll.setBorderType_(NSBezelBorder)
    scroll.setHasVerticalScroller_(True)
    scroll.setHasHorizontalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    scroll.setDocumentView_(document_view)
    return scroll


def update_results(text: str) -> Sequence[str]:
    """Convenience wrapper primarily used in tests."""

    return render_results(text.splitlines())


__all__ = ["ToolbarApp", "update_results"]
