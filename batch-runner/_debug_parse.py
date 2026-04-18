from pathlib import Path

from parse_labels import iter_samples

if __name__ == "__main__":
    writing = Path(__file__).resolve().parents[1] / "writing"
    for s in iter_samples(writing / "label_cn.txt", "cn"):
        if s.image_file == "0001.jpg":
            print("image:", s.image_file)
            print("title_len:", len(s.essay_title))
            print("title_head:", s.essay_title[:80])
            print("title_tail:", s.essay_title[-80:])
            break

