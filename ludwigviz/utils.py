import datetime
import re
import json
import pandas as pd
from pandas.core.groupby.groupby import DataError
from typing import List
try:
    import altair
except TypeError:
    raise RuntimeError('altair requires Python > =3.5.3')


from ludwigviz import configs

regex_digit = re.compile(r'[0-9]+')


def make_json_chart(data: pd.DataFrame,
                    column_name: str,
                    title: str,
                    ) -> dict:
    """
    Example data:
        mean_ accuracy param_name
        0             1.00    param_1
        10            2.00    param_1
        20            3.00    param_1
        30            4.25    param_1
        0             1.00    param_2
        10            2.00    param_2
        20            3.00    param_2
        30            6.00    param_2

    this "long-format" is necessary for altair to plot multiple lines
    (each is associated with a unique param_name)

    """
    # make index available for plotting (https://altair-viz.github.io/user_guide/data.html)
    data = data.reset_index()  # inserts new column which was previously the index with col-name="index"
    data.rename(columns={'index': configs.Chart.x_name}, inplace=True)

    # y-scale
    try:
        y_lims = configs.Chart.name2y_lims[column_name.lstrip('mean_')]
    except KeyError:
        y_scale = altair.Scale(zero=False)
    else:
        print('Using custom y-axis limits')
        y_scale = altair.Scale(domain=y_lims)

    # make interactive chart and convert to json object
    chart = altair.Chart(data).mark_line().encode(
        x=f'{configs.Chart.x_name}:Q',
        y=altair.Y(column_name, scale=y_scale),
        color='param_name'
    ).interactive()

    # to json
    json_str = chart.to_json()
    json_chart = json.loads(json_str)

    # set title and size
    json_chart['config']['view']['height'] *= configs.Chart.scale_factor
    json_chart['config']['view']['width'] *= configs.Chart.scale_factor
    json_chart['title'] = title
    return json_chart


def aggregate_data(project_name: str,
                   param_names: List[str],
                   pattern: str,
                   verbose: bool = False,
                   ) -> pd.DataFrame:
    mean_dfs = []
    for param_name in sorted(param_names, key=lambda n: int(n[6:])):
        # get all series matching pattern
        # squeeze=True tells pandas to return series
        param_path = to_param_path(project_name, param_name)
        series_list = [pd.read_csv(p, index_col=0, squeeze=True) for p in param_path.rglob(pattern)]
        # average columns with the same name
        try:
            concatenated_df = pd.concat((s for s in series_list if len(s) > 1), axis=1)
        except DataError:  # cannot group because data is malformed
            raise ValueError  # to be caught by outside scope
        mean_df = concatenated_df.groupby(by=concatenated_df.columns, axis=1).mean()
        mean_df['param_name'] = f'param_{to_param_id(param_name):0>3}'  # zero-padding
        # rename
        old_name = mean_df.columns[0]
        new_name = 'mean_{}'.format(old_name)
        mean_df.rename(columns={old_name: new_name}, inplace=True)
        # collect
        mean_dfs.append(mean_df)

    res = pd.concat(mean_dfs, axis=0)  # raises Value error if list is empty

    if verbose:
        print(res)

    return res


def to_param_path(project_name, param_name):
    return configs.Dirs.ludwig_data / project_name / 'runs' / param_name


def sort_rows(rows, header, order):

    assert header in rows[0]  # make sure that the header is actually in use

    if header == 'Last Modified':
        print('Sorting using datetime')
        res = sorted(rows,
                     key=lambda row: datetime.datetime.strptime(row[header], configs.Time.format),
                     reverse=True if order == 'descending' else False)
    else:
        res = sorted(rows,
                     key=lambda row: row[header],
                     reverse=True if order == 'descending' else False)
    return res


def to_param_id(param_name):
    return regex_digit.search(param_name).group()


def get_time_modified(p):
    return datetime.datetime.fromtimestamp(
        p.lstat().st_mtime).strftime(configs.Time.format)