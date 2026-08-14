"""
TODO
"""

import argparse
import os
import re
import tomllib

from pathlib import Path


def load_toml_config(toml_path):
    """
    TODO
    """
    with open(toml_path, "rb") as f:
        config = tomllib.load(f)
    return config


def get_all_repo_content(content_root):
    """
    TODO
    """
    content = set()
    for dirname, _, files in os.walk(content_root):
        for file in files:
            filename = os.path.join(dirname, file)
            content.add(filename)
    return content


def get_excluded_dir_files(exclusions):
    """
    TODO
    """
    # Collect a list of excluded files based on directory targets
    content = set()
    for exclusion in exclusions:
        for dirname, _, files in os.walk(exclusion):
            for file in files:
                filename = os.path.join(dirname, file)
                content.add(filename)
    return content


def get_all_excluded_files(config, config_keys):
    """
    TODO
    """
    excluded_files = set()
    for config_key in config_keys:
        excluded_files.update(set(config[config_key]["excluded_files"]))
        excluded_files.update(
            get_excluded_dir_files(config["docs_general"]["excluded_directories"])
        )
    return excluded_files


def get_filtered_files(config, config_keys):
    """
    TODO
    """
    filtered_files = {}
    filtered_files["excluded_files"] = get_all_excluded_files(config, config_keys)
    filtered_files["all_files"] = get_all_repo_content(
        config["docs_general"]["content_root"]
    )
    filtered_files["all_files_in_scope"] = set(
        [
            item
            for item in filtered_files["all_files"]
            if item not in filtered_files["excluded_files"]
        ]
    )
    filtered_files["doc_files"] = set(
        filter(lambda x: x.endswith(".md"), filtered_files["all_files"])
    )
    filtered_files["doc_files_in_scope"] = [
        item
        for item in filtered_files["doc_files"]
        if item not in filtered_files["excluded_files"]
    ]
    return filtered_files


def get_document_links(document):
    """
    TODO
    """
    content = None
    with open(document) as fh:
        content = fh.read()

    # non-greedy search for all link structures like
    # [title](./img/foo.png). will strip any leading ./
    pattern = re.compile(r"\[.*?\]\((.*?)\)")
    matches = pattern.findall(content)

    links = set()
    for match in matches:
        if match.startswith("http") or match.startswith("#"):
            continue
        link = match.split("#")[0]
        if link.startswith("./"):
            link = link.replace("./", "")
        links.add(link)
    return links


def get_resolved_path(file_directory, relative_link):
    """
    TODO
    """
    up_tree_steps = relative_link.count("../")
    full_dir_path = Path("/".join(file_directory.split("/")[0:-up_tree_steps]))
    stripped_link = Path("/".join(relative_link.replace("../", "").split("/")))
    content_path_obj = full_dir_path / stripped_link
    content_path = "./" + str(content_path_obj)
    return content_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="The config file to use as reference for the script",
    )

    args = parser.parse_args()
    # Ensure a config was passed to the script
    if not all([args.config]):
        print("ERROR: All arguments must be provided")
        parser.print_help()
        exit(1)
    # Test that the config file exists
    if not Path(args.config).is_file():
        print(f"ERROR: {args.config} is not a valid file.")
        exit(1)
    config = load_toml_config(args.config)

    # Provide all files and doc files in scope
    config_keys = ["docs_general", "orphaned_content"]
    filtered_files = get_filtered_files(config, config_keys)

    # Discover all Markdown links
    linked_files = set()
    for doc_file in filtered_files["doc_files_in_scope"]:
        file_directory = os.path.dirname(doc_file)
        links = get_document_links(doc_file)

        for link in links:
            # Help resolve relative link paths
            if link.startswith("../"):
                content_path = get_resolved_path(file_directory, link)
            else:
                content_path = str(Path(file_directory) / link)
            if not content_path.startswith("."):
                content_path = f"./{content_path}"
            linked_files.add(content_path)

    # Discover all unlinked Markdown files
    unlinked_files = (
        filtered_files["all_files_in_scope"]
        - linked_files
        - set(config["orphaned_content"]["unlinked_file_exceptions"])
        - set(config["orphaned_content"]["toc_files_to_validate"])
    )

    # Discover all unlinked Markdown files in the TOC(s)
    toc_md_links = set()
    for toc_file in config["orphaned_content"]["toc_files_to_validate"]:
        toc_md_links.update(get_document_links(toc_file))
    # Convert relative path links to include content root prefix
    toc_md_files_in_scope = set(
        [
            f"{config['docs_general']['content_root']}/{md_file_path}"
            for md_file_path in toc_md_links
        ]
    )
    unlinked_files_in_toc = (
        set(filtered_files["doc_files_in_scope"])
        - toc_md_files_in_scope
        - set(config["orphaned_content"]["unlinked_file_exceptions"])
        - set(config["orphaned_content"]["toc_files_to_validate"])
    )

    errors = False
    # If any unlinked files discovered, print and throw error
    if len(unlinked_files):
        print("Found the following unlinked %d file(s):" % len(unlinked_files))
        for unlinked_file in sorted(unlinked_files):
            print(unlinked_file)
        errors = True

    # If any unlinked files discovered, that aren't in the TOC, print and throw error
    if len(unlinked_files_in_toc):
        print(
            "Found the following %d file(s) missing from the TOC(s):"
            % len(unlinked_files_in_toc)
        )
        for unlinked_file in sorted(unlinked_files_in_toc):
            print(unlinked_file)
        errors = True

    if errors:
        exit(1)


if __name__ == "__main__":
    main()
