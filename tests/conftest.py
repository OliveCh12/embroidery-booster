import pytest


@pytest.fixture
def svg_file(tmp_path):
    def write(content, *, width="240", height="140", viewbox=None, name="shape.svg"):
        path = tmp_path / name
        attrs = f'width="{width}" height="{height}"'
        if viewbox:
            attrs += f' viewBox="{viewbox}"'
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}>{content}</svg>')
        return path

    return write
