"""Private start/publish defaults and safe, one-time planning seeds."""
import nbformat
import pytest
from test_content_service import content_service as content_service

from watchtower.models import Artifact, eligible, markdown_h1s
from watchtower.services.workspace import ServiceError
from watchtower.starters import draft_sections


@pytest.mark.parametrize('kind', ['post', 'portfolio', 'course', 'chapter', 'personal'])
@pytest.mark.parametrize('visibility', ['public', 'private'])
@pytest.mark.parametrize('mode', ['preview', 'production'])
def test_plans_are_never_frontend_eligible(kind, visibility, mode):
    extra = {'parent': 'course/parent', 'section': 'main', 'toc_title': 'Short'} if kind == 'chapter' else {}
    artifact = Artifact(id=f'{kind}/plan', kind=kind, title='Plan', path='content/notebooks/courses/plan' if kind == 'course' else f'content/notebooks/{kind}/plan.ipynb', visibility=visibility, **extra)
    parent = Artifact(id='course/parent', kind='course', title='Parent', path='content/notebooks/courses/parent', lifecycle='published')
    assert not eligible(artifact, [artifact, parent], mode)


def test_start_and_publish_defaults_and_later_plan_edits(content_service):
    service = content_service
    created = service.create_post('flow', {'title': 'Flow', 'visibility': 'public', 'planned': {'content': 'Explain the example.'}, 'internal_notes': 'Private notes'})
    assert created['artifact']['visibility'] == 'private'
    started = service.start('post/flow', created['revision'])
    assert started['artifact']['visibility'] == 'private'
    path = service.root / started['source_path']
    before = path.read_bytes()
    assert b'Explain the example.' in before
    assert b'Private todo' not in before and b'Private notes' not in before
    # An untouched seed follows the plan; the first hand edit freezes the draft.
    service.update('post/flow', {'planned': {'content': 'A revised plan'}})
    refreshed = path.read_bytes()
    assert b'A revised plan' in refreshed and b'Explain the example.' not in refreshed
    assert b'Private todo' not in refreshed and b'Private notes' not in refreshed
    notebook = nbformat.read(path, as_version=4)
    notebook.cells.append(nbformat.v4.new_markdown_cell('My own prose.'))
    path.write_bytes(nbformat.writes(notebook).encode())
    edited = path.read_bytes()
    service.update('post/flow', {'planned': {'content': 'An ignored plan edit'}})
    assert path.read_bytes() == edited
    with pytest.raises(ServiceError):
        service.publish('post/flow', started['revision'])
    assert service.inspect('post/flow')['artifact']['visibility'] == 'private'
    published = service.publish('post/flow')
    assert published['artifact']['lifecycle'] == 'published'
    assert published['artifact']['visibility'] == 'public'
    assert service.inspect('post/flow')['eligible']
    assert path.read_bytes() == edited


def test_starter_demotes_h1s_and_preserves_fences_and_lists():
    outline = '# Topic\n\nHeading\n=======\n\n```markdown\n# Fenced example\n```'
    sections = draft_sections('post', {'content': outline, 'next_steps': 'SECRET', 'extension': 'SECRET'})
    assert markdown_h1s('\n\n'.join(sections)) == []
    assert '## Topic' in sections[0]
    assert '```markdown\n# Fenced example\n```' in sections[0]
    assert 'SECRET' not in ''.join(sections)
    assert draft_sections('course', {'outcomes': ['Build it', 'Test it']}) == ['## Learning outcomes\n\n- Build it\n- Test it']
    assert draft_sections('post', {'content': '  \n '}) == []


def test_oversized_block_start_is_atomic(content_service):
    service = content_service
    service.create_post('large', {'title': 'Large', 'planned': {'content': '```python\n' + 'x' * 20_000 + '\n```'}})
    before = service.snapshot().revision
    with pytest.raises(ServiceError, match='split it before starting'):
        service.start('post/large')
    assert service.snapshot().revision == before
    assert not (service.root / 'content/notebooks/posts/large.ipynb').exists()


def test_empty_plan_stays_unpublishable(content_service):
    service = content_service
    service.create_post('empty', {'title': 'Empty', 'planned': {'next_steps': 'Write it'}})
    started = service.start('post/empty')
    notebook = nbformat.read(service.root / started['source_path'], as_version=4)
    assert [cell.source for cell in notebook.cells] == ['# Empty\n']
    with pytest.raises(ServiceError):
        service.publish('post/empty')
    assert service.inspect('post/empty')['artifact']['visibility'] == 'private'


@pytest.mark.parametrize('abstract,description,expected', [
    (None, None, 'A tool for comparing models. Reports and reproducible evaluations.'),
    ('', None, 'A tool for comparing models. Reports and reproducible evaluations.'),
    ('Handwritten abstract.', 'Old description.', 'Handwritten abstract.'),
    (None, 'Existing summary.', 'Existing summary.'),
])
def test_portfolio_start_seeds_only_missing_abstract(content_service, abstract, description, expected):
    service = content_service
    service.create({'id': 'portfolio/summary', 'kind': 'portfolio', 'title': 'Summary', 'description': description,
                    'detail': {'abstract': abstract, 'planned': {'introduction': '## Problem\n\nA **tool** for comparing models.\n\nMore detail.', 'what_it_contains': 'Reports and reproducible evaluations.', 'scope_notes': 'INTERNAL', 'next_steps': 'INTERNAL'}}})
    service.start('portfolio/summary')
    assert service.inspect('portfolio/summary')['detail']['abstract'] == expected
    service.update('portfolio/summary', {'detail': {'planned': {'introduction': 'Later plan'}}})
    assert service.inspect('portfolio/summary')['detail']['abstract'] == expected


def test_abstract_seed_is_bounded_and_ignores_nonprose():
    from watchtower.starters import portfolio_abstract
    assert portfolio_abstract({'introduction': '# Heading\n\n```python\nsecret()\n```', 'scope_notes': 'SECRET'}) == ''
    assert portfolio_abstract({'introduction': 'Same paragraph.', 'what_it_contains': 'Same paragraph.'}) == 'Same paragraph.'
    text = portfolio_abstract({'introduction': 'word ' * 100})
    assert len(text.split()) == 80 and text.endswith('…')


def test_draft_notebook_cells_seed_title_sections_and_references():
    from watchtower.starters import draft_notebook_cells
    cells = draft_notebook_cells('portfolio', 'Signal filters', {
        'introduction': 'Filters drift.', 'references': 'ref1\nref2',
        'scope_notes': 'INTERNAL', 'next_steps': 'INTERNAL',
    })
    assert cells[0] == '# Signal filters\n'
    assert cells[1].startswith('## The problem')
    assert cells[-1] == '## References\n\n- ref1\n- ref2'
    joined = '\n'.join(cells)
    assert 'INTERNAL' not in joined
    assert draft_notebook_cells('portfolio', 'Title only', {}) == ['# Title only\n']


def test_plain_reference_lines_seed_as_a_list():
    from watchtower.starters import draft_sections
    assert draft_sections('portfolio', {'references': 'ref1\nref2\nref3'}) == ['## References\n\n- ref1\n- ref2\n- ref3']
    assert draft_sections('post', {'references': 'ref1\nref2'}) == ['## References\n\n- ref1\n- ref2']
    # Authored Markdown keeps its own structure.
    assert draft_sections('portfolio', {'references': 'Paragraph one.\n\nParagraph two.'}) == ['## References\n\nParagraph one.\n\nParagraph two.']
    assert draft_sections('portfolio', {'references': '> quoted reference'}) == ['## References\n\n> quoted reference']


def test_portfolio_project_path_defaults_to_the_portfolio_name(content_service):
    service = content_service
    service.create({'id': 'portfolio/named', 'kind': 'portfolio', 'title': 'Named', 'detail': {'planned': {}}})
    assert service.inspect('portfolio/named')['detail']['project_path'] == 'projects/named'
    service.create({'id': 'portfolio/aliased', 'kind': 'portfolio', 'title': 'Aliased', 'detail': {'project_path': 'projects/shared-code', 'planned': {}}})
    assert service.inspect('portfolio/aliased')['detail']['project_path'] == 'projects/shared-code'


def test_plan_save_reseeds_only_unedited_scaffolds(content_service):
    service = content_service
    created = service.create({'id': 'portfolio/late', 'kind': 'portfolio', 'title': 'Late', 'detail': {'planned': {}}})
    started = service.start('portfolio/late', created['revision'])
    source = service.root / started['source_path']
    assert [cell.source for cell in nbformat.read(source, as_version=4).cells] == ['# Late\n']
    service.update('portfolio/late', {'detail': {'planned': {'introduction': 'The problem to solve.', 'what_it_contains': 'A checked pipeline.', 'references': 'ref1\nref2'}}})
    cells = [cell.source for cell in nbformat.read(source, as_version=4).cells]
    assert cells[0] == '# Late\n' and 'The problem to solve.' in cells[1]
    assert cells[-1] == '## References\n\n- ref1\n- ref2'
    assert service.inspect('portfolio/late')['detail']['abstract'] == 'The problem to solve. A checked pipeline.'
    # Authored content ends re-seeding; later plan edits never rewrite the notebook.
    notebook = nbformat.read(source, as_version=4)
    notebook.cells.append(nbformat.v4.new_markdown_cell('My own prose.'))
    source.write_bytes(nbformat.writes(notebook).encode())
    before = source.read_bytes()
    service.update('portfolio/late', {'detail': {'planned': {'introduction': 'A changed problem.'}}})
    assert source.read_bytes() == before
    assert service.inspect('portfolio/late')['detail']['abstract'] == 'The problem to solve. A checked pipeline.'


def test_reseed_never_overwrites_an_explicit_abstract(content_service):
    service = content_service
    service.create({'id': 'portfolio/kept', 'kind': 'portfolio', 'title': 'Kept', 'detail': {'abstract': 'Handwritten.', 'planned': {}}})
    service.start('portfolio/kept')
    service.update('portfolio/kept', {'detail': {'planned': {'introduction': 'A problem.'}}})
    saved = service.inspect('portfolio/kept')
    assert saved['detail']['abstract'] == 'Handwritten.'
    cells = [cell.source for cell in nbformat.read(service.root / saved['source_path'], as_version=4).cells]
    assert any('A problem.' in cell for cell in cells)


def test_rename_keeps_scaffold_titles_in_sync_and_reseeds(content_service):
    service = content_service
    created = service.create_post('renamed', {'title': 'Old title', 'planned': {'content': 'Body plan.'}})
    started = service.start('post/renamed', created['revision'])
    source = service.root / started['source_path']
    # A seeded draft's title H1 follows coordinated renames, so the page shows the title once.
    service.update('post/renamed', {'title': 'New title'})
    cells = [cell.source for cell in nbformat.read(source, as_version=4).cells]
    assert cells[0].strip() == '# New title' and any('Body plan.' in cell for cell in cells)
    # A combined rename and plan save still re-seeds a title-only scaffold.
    service.create_post('combined', {'title': 'Old title', 'planned': {}})
    service.start('post/combined')
    service.update('post/combined', {'title': 'Renamed', 'planned': {'content': 'Seeded body.'}})
    cells = [cell.source for cell in nbformat.read(service.root / 'content/notebooks/posts/combined.ipynb', as_version=4).cells]
    assert cells[0] == '# Renamed\n' and any('Seeded body.' in cell for cell in cells)
