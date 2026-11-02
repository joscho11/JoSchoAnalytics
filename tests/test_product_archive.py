"""Public archive behavior without changing the preserved product renderers."""
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import nav_registry

os.environ['APP_OFFLINE'] = '1'
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {
    'anytime-tds': 'page_anytime_td',
    'college-basketball': 'page_cbb_daily',
}


@pytest.fixture(autouse=True)
def current_navigation_source(monkeypatch):
    # Model a module loaded from the current source while tests toggle settings.
    monkeypatch.setattr(nav_registry, '__joscho_source_mtime_ns__',
                        Path(nav_registry.__file__).stat().st_mtime_ns, raising=False)


def copy(at):
    return ' '.join(str(element.value) for kind in ('markdown', 'caption', 'info')
                    for element in getattr(at, kind))


def clean(at):
    assert not at.exception, at.exception
    assert not at.error, [error.value for error in at.error]
    return at


def switch(at, slug):
    # Callable st.Pages have no script path for AppTest.switch_page().
    at._page_hash = nav_registry.PAGES[slug]._script_hash
    return clean(at.run())


@pytest.mark.parametrize('slug', PRODUCTS)
def test_paused_route_avoids_product_import_and_returns_home(slug, monkeypatch):
    real_import = importlib.import_module

    def guarded_import(name, *args, **kwargs):
        assert name not in {*PRODUCTS.values(), 'cbb_daily_data'}, name
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, 'import_module', guarded_import)
    at = clean(AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run())
    assert nav_registry.PAGES[slug]._visibility == 'hidden'
    at.query_params.update({'atd_year': '2026', 'atd_week': '6'})
    switch(at, slug)
    assert 'This product is paused' in copy(at)
    assert not at.selectbox and not at.dataframe
    link = next(link for link in at.get('page_link') if link.label == 'Back to Home')
    assert link.page_script_hash == nav_registry.PAGES['home']._script_hash
    switch(at, 'home')
    assert at.title[0].value == 'JoScho Analytics'


@pytest.mark.parametrize('slug,module', PRODUCTS.items())
def test_removing_one_archive_setting_restores_only_that_product(slug, module, monkeypatch):
    monkeypatch.setattr(nav_registry, 'ARCHIVED_PAGES', frozenset(PRODUCTS) - {slug})
    real_import = importlib.import_module
    # The application installs the selected renderer in sys.modules; restore the
    # real module after using a stub so downstream product tests stay isolated.
    monkeypatch.setitem(sys.modules, module, real_import(module))
    calls = []

    def import_product(name, *args, **kwargs):
        if name == module:
            calls.append(name)
            return SimpleNamespace(render=lambda: st.write('Restored product renderer'))
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, 'import_module', import_product)
    groups = {}
    real_navigation = st.navigation

    def navigation(pages, **kwargs):
        groups.update(pages)
        return real_navigation(pages, **kwargs)

    monkeypatch.setattr(st, 'navigation', navigation)
    at = clean(AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run())
    assert nav_registry.PAGES[slug]._visibility == 'visible'
    other = next(key for key in PRODUCTS if key != slug)
    assert nav_registry.PAGES[other]._visibility == 'hidden'
    assert ('College Basketball' in groups) == (slug == 'college-basketball')
    switch(at, slug)
    assert calls == [module]
    assert 'Restored product renderer' in copy(at)
    assert 'This product is paused' not in copy(at)


def test_archived_navigation_has_no_empty_college_menu(monkeypatch):
    groups = {}
    real_navigation = st.navigation

    def navigation(pages, **kwargs):
        groups.update(pages)
        return real_navigation(pages, **kwargs)

    monkeypatch.setattr(st, 'navigation', navigation)
    clean(AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run())
    assert list(groups) == ['', 'Betting', 'Fantasy', 'More']
    pages = [page for group in groups.values() for page in group]
    assert len(pages) == len(set(page._script_hash for page in pages))
    assert [page.url_path for page in pages if page._visibility == 'hidden'] == [
        'anytime-tds', 'film-room', 'college-basketball',
    ]


@pytest.mark.parametrize('today', ['2026-08-24', '2026-11-01'])
def test_home_week_and_help_promotions_follow_archive_setting(today, monkeypatch):
    monkeypatch.setenv('APP_TODAY', today)
    for archived in (True, False):
        monkeypatch.setattr(nav_registry, 'ARCHIVED_PAGES', frozenset(PRODUCTS) if archived else frozenset())
        at = clean(AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run())
        assert ('Compare touchdown props' in copy(at)) == (not archived)
        switch(at, 'this-week')
        assert ('### Touchdown Props' in copy(at)) == (not archived)
        switch(at, 'help')
        directory_links = ' '.join(link.label for link in at.get('page_link'))
        assert ('Anytime, 2+, and First TD scorer probabilities' in directory_links) == (not archived)


def test_td_methodology_is_explicitly_historical(tmp_path):
    harness = tmp_path / 'historical_td_methodology.py'
    harness.write_text('import help_models\nhelp_models._anytime_td()\n', encoding='utf-8')
    at = clean(AppTest.from_file(str(harness)).run())
    assert 'historical, paused' in at.expander[0].label
    assert 'Historical methodology' in copy(at)
    assert 'current live release' not in copy(at)
    assert 'New live slates are appended' not in copy(at)



@pytest.mark.parametrize('width', [390, 768, 1440])
def test_browser_hidden_navigation_and_old_urls(browser, app_url, width):
    from playwright_support import open_route, wait_for_app

    context = browser.new_context(viewport={'width': width, 'height': 900},
                                  is_mobile=width < 768, has_touch=width < 768)
    try:
        page = context.new_page()
        # Screenshot stabilization hides Streamlit's toolbar, including the
        # drawer trigger. Exercise real navigation before applying that CSS.
        page.goto(app_url + '/', wait_until='domcontentloaded')
        wait_for_app(page)
        if width < 768:
            page.locator('[data-testid="stExpandSidebarButton"]').click()
        # Hidden products and the empty CBB section must not be discoverable.
        assert page.get_by_text('College Basketball', exact=True).count() == 0
        assert page.get_by_role('link', name='Touchdown Props (Beta)', exact=True).count() == 0
        if width < 768:
            page.locator('[data-testid="stSidebarCollapseButton"]').click()
            page.wait_for_function("document.querySelector('[data-testid=\"stSidebar\"]').getAttribute('aria-expanded') === 'false'")
        for slug in PRODUCTS:
            open_route(page, app_url, slug, 'atd_year=2026&atd_week=6')
            assert page.get_by_text('This product is paused', exact=True).is_visible()
            assert page.locator('[data-testid="stDataFrame"]').count() == 0
            page.get_by_role('link', name='Back to Home').click()
            wait_for_app(page)
            page.get_by_role('heading', name='JoScho Analytics', exact=True).wait_for(state='visible')
    finally:
        context.close()



def test_warm_cloud_refresh_recovers_archive_settings(monkeypatch):
    monkeypatch.delattr(nav_registry, 'is_archived')
    monkeypatch.delattr(nav_registry, 'ARCHIVED_PAGES')
    at = clean(AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run())
    assert nav_registry.is_archived('anytime-tds')
    switch(at, 'anytime-tds')
    assert 'This product is paused' in copy(at)
