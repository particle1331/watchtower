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
    created = service.create_post('flow', {'title': 'Flow', 'visibility': 'public', 'planned': {'content': 'Explain the example.'}})
    assert created['artifact']['visibility'] == 'private'
    started = service.start('post/flow', created['revision'])
    assert started['artifact']['visibility'] == 'private'
    path = service.root / started['source_path']
    before = path.read_bytes()
    assert b'Explain the example.' in before
    with pytest.raises(ServiceError, match='plan has been consumed'):
        service.update('post/flow', {'planned': {'content': 'A revised plan'}})
    assert path.read_bytes() == before
    service.update('post/flow', {'internal_notes': '## Notes\n\nPrivate notes\n\n## To-dos\n\n- [ ] Add an example'})
    assert path.read_bytes() == before
    with pytest.raises(ServiceError):
        service.publish('post/flow', started['revision'])
    published = service.publish('post/flow')
    assert published['artifact']['lifecycle'] == 'published'
    assert published['artifact']['visibility'] == 'public'
    assert service.inspect('post/flow')['eligible']
    assert path.read_bytes() == before


def test_starter_demotes_h1s_and_preserves_fences_and_lists():
    outline = '# Topic\n\nHeading\n=======\n\n```markdown\n# Fenced example\n```'
    sections = draft_sections('post', {'content': outline, 'next_steps': 'SECRET', 'extension': 'SECRET'})
    assert markdown_h1s('\n\n'.join(sections)) == []
    assert '## Topic' in sections[0]
    assert '```markdown\n# Fenced example\n```' in sections[0]
    assert 'SECRET' not in ''.join(sections)
    # Course plans are the CMS course home; they never seed notebook sections.
    assert draft_sections('course', {'outcome': 'Build it'}) == []
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
    with pytest.raises(ServiceError, match='plan has been consumed'):
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
    assert cells[-1] == '## Planned evidence\n\n### References\n\n- ref1\n- ref2'
    joined = '\n'.join(cells)
    assert 'INTERNAL' not in joined
    assert draft_notebook_cells('portfolio', 'Title only', {}) == ['# Title only\n']


def test_plain_reference_lines_seed_as_a_list():
    from watchtower.starters import draft_sections
    assert draft_sections('portfolio', {'references': 'ref1\nref2\nref3'}) == ['## Planned evidence\n\n### References\n\n- ref1\n- ref2\n- ref3']
    assert draft_sections('post', {'references': 'ref1\nref2'}) == ['## Planned evidence\n\n### References\n\n- ref1\n- ref2']
    # Authored Markdown keeps its own structure.
    assert draft_sections('portfolio', {'references': 'Paragraph one.\n\nParagraph two.'}) == ['## Planned evidence\n\n### References\n\nParagraph one.\n\nParagraph two.']
    assert draft_sections('portfolio', {'references': '> quoted reference'}) == ['## Planned evidence\n\n### References\n\n> quoted reference']


def test_portfolio_legacy_brief_folds_into_three_sections_without_losing_saved_text():
    from watchtower.planning import portfolio_plan
    legacy = {'introduction': 'Problem.', 'what_it_contains': 'Components.', 'intended_users': 'Users.',
              'approach': 'Design.', 'success_criteria': 'Passing checks.', 'references': 'Source one\nSource two'}
    original = dict(legacy)
    plan = portfolio_plan(legacy)
    cells = draft_sections('portfolio', plan)
    assert [cell.splitlines()[0] for cell in cells] == ['## The problem', '## Planned content', '## Planned evidence']
    assert all(text in '\n\n'.join(cells) for text in ('Components.', 'Users.', 'Design.', 'Passing checks.', 'Source one', 'Source two'))
    assert legacy == original
    assert all(plan[key] == value for key, value in legacy.items())
    assert portfolio_plan({**legacy, 'content': '', 'evidence': 'Explicit evidence.'})['content'] == ''
    assert draft_sections('portfolio', {**legacy, 'content': 'New content.', 'evidence': 'New evidence.'}) == [
        '## The problem\n\nProblem.', '## Planned content\n\nNew content.', '## Planned evidence\n\nNew evidence.']


def test_portfolio_project_path_defaults_to_the_portfolio_name(content_service):
    service = content_service
    service.create({'id': 'portfolio/named', 'kind': 'portfolio', 'title': 'Named', 'detail': {'planned': {}}})
    assert service.inspect('portfolio/named')['detail']['project_path'] == 'projects/named'
    service.create({'id': 'portfolio/aliased', 'kind': 'portfolio', 'title': 'Aliased', 'detail': {'project_path': 'projects/shared-code', 'planned': {}}})
    assert service.inspect('portfolio/aliased')['detail']['project_path'] == 'projects/shared-code'


@pytest.mark.parametrize('abstract', [None, 'Handwritten.'])
def test_empty_scaffolds_never_reseed_after_start(content_service, abstract):
    service = content_service
    service.create({'id': 'portfolio/late', 'kind': 'portfolio', 'title': 'Late', 'detail': {'abstract': abstract, 'planned': {}}})
    started = service.start('portfolio/late')
    source = service.root / started['source_path']
    before = source.read_bytes()
    revision = service.snapshot().revision
    with pytest.raises(ServiceError, match='plan has been consumed'):
        service.update('portfolio/late', {'detail': {'planned': {'introduction': 'A new problem.'}}})
    assert source.read_bytes() == before
    assert service.snapshot().revision == revision
    assert service.inspect('portfolio/late')['detail']['abstract'] == abstract


def test_rename_keeps_scaffold_titles_in_sync_without_reseeding(content_service):
    service = content_service
    created = service.create_post('renamed', {'title': 'Old title', 'planned': {'content': 'Body plan.'}})
    started = service.start('post/renamed', created['revision'])
    source = service.root / started['source_path']
    # A seeded draft's title H1 follows coordinated renames, so the page shows the title once.
    service.update('post/renamed', {'title': 'New title'})
    cells = [cell.source for cell in nbformat.read(source, as_version=4).cells]
    assert cells[0].strip() == '# New title' and any('Body plan.' in cell for cell in cells)
    # A combined rename and plan write is rejected atomically, even for title-only drafts.
    service.create_post('combined', {'title': 'Old title', 'planned': {}})
    service.start('post/combined')
    source = service.root / 'content/notebooks/posts/combined.ipynb'
    before = source.read_bytes()
    with pytest.raises(ServiceError, match='plan has been consumed'):
        service.update('post/combined', {'title': 'Renamed', 'planned': {'content': 'Seeded body.'}})
    assert source.read_bytes() == before
    assert service.inspect('post/combined')['artifact']['title'] == 'Old title'


def _plan_for(kind):
    if kind == 'post':
        return {'content': 'Outline body.', 'audience': 'Readers.', 'evidence': 'Evidence.', 'references': '- Ref one\n- Ref two'}
    if kind == 'portfolio':
        return {'introduction': 'The problem.', 'what_it_contains': 'Contents.', 'intended_users': 'Users.',
                'approach': 'Approach.', 'success_criteria': 'Criteria.', 'references': '- Ref one'}
    return {'content': 'Explain the idea.', 'lab_and_evidence': 'Practice the idea.'}


@pytest.mark.parametrize('kind', ['post', 'portfolio', 'chapter'])
def test_plan_preview_is_exactly_the_started_draft_body(content_service, kind):
    """The plan page and the draft page share one body: the draft is definitive."""
    service = content_service
    if kind == 'chapter':
        service.create({'id': 'course/demo', 'kind': 'course', 'title': 'Demo course', 'path': 'content/notebooks/courses/demo',
                        'contract': {'planned': {'outcome': 'Build', 'description': 'Teach', 'chapters': []}}})
        service.start('course/demo')
        service.create({'id': 'course/demo/first', 'kind': 'chapter', 'title': 'First', 'parent': 'course/demo', 'section': 'main',
                        'toc_title': 'First', 'path': 'content/notebooks/courses/demo/first.ipynb', 'plan': _plan_for(kind)})
        identifier = 'course/demo/first'
    elif kind == 'post':
        identifier = 'post/guard'
        service.create({'id': identifier, 'kind': 'post', 'title': 'Guard', 'path': 'content/notebooks/posts/guard.ipynb', 'planned': _plan_for(kind)})
    else:
        identifier = 'portfolio/guard'
        service.create({'id': identifier, 'kind': 'portfolio', 'title': 'Guard', 'detail': {'planned': _plan_for(kind)}})
    plan = service.inspect(identifier)['plan']
    started = service.start(identifier)
    notebook = nbformat.read(service.root / started['source_path'], as_version=4)
    cells = [cell.source.strip() for cell in notebook.cells]
    # Generated pages drop a title H1 that repeats the catalog title, except chapters, which keep it.
    expected = '\n\n'.join(cells if kind == 'chapter' else cells[1:])
    assert plan == expected
    assert service.inspect(identifier)['plan'] == ''


def test_plan_labels_are_the_draft_headings():
    from watchtower.planning import PLAN, parse_plan_file
    from watchtower.starters import SECTIONS
    for kind in ('post', 'portfolio', 'chapter'):
        labels = {field.key: field.label for field in PLAN[kind]}
        for key, heading in SECTIONS[kind]:
            if heading:
                assert labels[key] == heading, (kind, key)
    # Earlier labels still work in existing plan files.
    assert parse_plan_file('portfolio', '## Problem\n\nWhy.\n\n## Success criteria\n\nHow.') == {'introduction': 'Why.', 'evidence': 'How.'}
    assert parse_plan_file('post', '## Outline\n\nContent.\n\n## Examples and evidence\n\nEvidence.') == {'content': 'Content.', 'evidence': 'Evidence.'}
    assert parse_plan_file('chapter', '## Outline\n\nContent.\n\n## Practice and evidence\n\nEvidence.') == {'content': 'Content.', 'lab_and_evidence': 'Evidence.'}
    assert draft_sections('chapter', {'content': 'Legacy outline.', 'lab_and_evidence': 'Legacy exercise.'}) == [
        '## Planned content\n\nLegacy outline.', '## Planned evidence\n\nLegacy exercise.']


def test_post_legacy_brief_folds_into_supported_sections_without_readding_text():
    from watchtower.planning import post_plan
    legacy = {'content': 'Outline.', 'audience': 'Readers.', 'evidence': 'Experiment.', 'references': 'Source one\nSource two'}
    normalized = post_plan(legacy)
    assert legacy == {'content': 'Outline.', 'audience': 'Readers.', 'evidence': 'Experiment.', 'references': 'Source one\nSource two'}
    assert all(normalized[key] == value for key, value in legacy.items() if key in {'audience', 'references'})
    assert post_plan(normalized) == normalized
    assert draft_sections('post', legacy) == ['## Planned content\n\nOutline.\n\n### Who this is for\n\nReaders.',
                                            '## Planned evidence\n\nExperiment.\n\n### References\n\n- Source one\n- Source two']
    assert draft_sections('post', {**normalized, 'content': '', 'evidence': 'Revised evidence.'}) == ['## Planned evidence\n\nRevised evidence.']
