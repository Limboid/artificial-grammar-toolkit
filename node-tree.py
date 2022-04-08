# Computatrum
# Copyright (c) 2022 Limboid LLC. MIT License. See LICENSE for details.
"""Artificial Grammar Toolkit
TODO: copy README intro

Please see the README for more details:
https://github.com/Limboid/artificial-grammar-toolkit
"""

from __future__ import annotations
from copy import deepcopy
import itertools

import random
from re import I
from typing_extensions import Self, Protocol
from typing import Dict, Iterator, List, Optional, Set, Tuple, Union, runtime_checkable


def _lazy_eval(var, **kwargs):
    """Lazy eval.

    Gets the value behind a variable `var` that may be
    - a zero position arg function
    - a string that identifies a variable in the local or global scope
    - a raw string

    NOTE: the zero position arg function is a special case. `leval` will NOT:
    - evaluate a statement expressed as a string ("print('hello')")
    - evaluate a zero position arg function expressed as a string ("exit")

    Args:
        var (str): Variable to evaluate.
        **kwargs: Keyword arguments to pass to the variable if it is a function.

    Returns:
        The evaluated value of the function
        or the local or global variable
        or the raw string.

    Raises:
        Exception: If the variable is not found in the local or global scope.
    """
    if callable(var):
        return var(**kwargs)
    elif isinstance(var, str):
        l, g = locals(), globals()
        if var in l:
            return l[var]
        elif var in g:
            return g[var]
        else:
            return var
    else:
        raise ValueError(f'Invalid lazy variable: {var}')


@runtime_checkable
class _can_execute(Protocol):
    def __call__(self, env, scope: dict, **kwargs) -> Optional[Dict]: ...


Template = Union[Set['Template'], Tuple['Template'], Dict[str, 'Template'],
                 Iterator['Template'], List['Template'], 'Node', str]


@runtime_checkable
class LazyTemplate(Protocol):
    # TODO: update signature
    def __call__(self, scope: dict, **kwargs) -> Node: pass


class Node:

    global_scope: dict = {}

    scope_key: str = "Node"

    children: List[Node] = None
    traversal_order: List[Node] = None  # includes self
    scope: dict

    def __new__(cls: type[Self], template: Template, **kwargs) -> Self:
        """Convenience constructor for psuedo context-free grammars

        Node (N) is an 'abstract' class for the following subclasses:
        - ConcatNode (C)
        - RepeatNode (R)
        - UnionNode (U)
            - OptionalNode (O)
        The symbol in parenthesis denotes a shorthand for the corresponding type.
        Node is 'abstract' in the sense that while it does have a constructor,
        it is meant to be initialized from subclasses. The __new__ method in `Node`
        is overridden to return an appropriate subclass depending on the template.

        The `template` arg can be a nested structure of any of the following:
        - node: Node: A single node.
        - string: str: If the string evaluates to a `Template`, then that object, otherwise,
            a StringNode with the string value.
        - fn: LazyTemplateFn: lazy template generation. kwargs are inherited from the
            parent Node. Useful for recursive grammars.
        - Set[Node]: Converted to UnionNode of set content.
        - Tuple[Union[[Node],int]]: Converted to a ConcatNode with children taken from
            the tuple content. 0 or 1 of the lists items may be an int. If 1 int is given,
            then that int is used for the `N` keyword argument of the ConcatNode constructor.
            See `ConcatNode` __init__ docstring for more details.
        - Dict[str, Any]: Converted to a ConcatNode using kwargs from dict. Useful for supplying
            in custom kwargs. See ConcatNode __init__ docstring for more details.
        - List[Union[[Node],int]]: optional value, optional concatenation, or empty.
            - If the list contains exactly one node, then it is converted to an OptionalNode
                with the node as its child.
            - If the list contains more than one node, then it is converted to an OptionalNode
                with a ConcatNode as its child. The list contents are used to initialize the
                ConcatNode. See the Tuple case above for more details.
            - If the list is empty, then an EmptyNode is returned.
        - Iter[Node] (|*nodes: List[Node]|): Lazy concatenation of nodes. Values inside
            banana brackets (only supported in the coconut language) are not evaluated until
            the node is initialized. This allows defining recursive grammars. Converted to a
            ConcatNode on initialization.

        Except for dict structures, keys for children are determined by the child's `scope_key`
        attribute. The scope is updated by: `scope[node.scope_key] = node`. By default, the
        scope_key is the class name.

        Args:
            template (Template): Template to initialize the node with.

        Returns:
            A subclass of TemplateNode: New TemplateNode.
        """
        if isinstance(template, Node):
            return Node  # cls.__new__(cls, [template], **kwargs)
        elif isinstance(template, str):
            return _lazy_eval(template, **kwargs)
        elif issubclass(template, LazyTemplate):
            return template(**kwargs)
        elif isinstance(template, set):
            return UnionNode(list(template), **kwargs)
        elif isinstance(template, tuple):
            ints = filter(lambda x: isinstance(x, int), template)
            N = ints[0] if len(ints) == 1 else None
            return ConcatNode(list(template), N=N, **kwargs)
        elif isinstance(template, dict):
            kwargs.update(template)
            return ConcatNode(**kwargs)
        elif isinstance(template, list):
            # TODO: implement the rules for 0, 1, 1+ items
            return OptionalNode(tuple(template), **kwargs)
        elif isinstance(template, Iterator):
            return Node(tuple(template), **kwargs)
        else:
            raise Exception('Invalid template type: {}'.format(type(template)))

    def __init__(self, exec_func: _can_execute = None) -> None:
        """Initializes a node. Meant to be called by/from subclasses.

        Args:
            exec_func (can_execute, optional): Function that is called when
                the node graph is executed.  Defaults to None. `exec_func`
                allows defining templates using type annotations like so:
                ```python
                @TemplateNode
                def MOUSE_ACTION(env, scope, **kwargs):
                    x, y = scope['x'], scope['y']
                    env.move_mouse(x, y)
                ```
        """
        self.exec_func = exec_func

    def generate(self,
                 scope: dict = None,
                 children: List[Node] = [],
                 traversal_order: List[Node] = None,
                 **kwargs) -> Optional[dict]:
        """Generates a particular instantiation of the node graph.

        NOTE: this is both a base method and a recursive method. Subclasses
        should call `super.generate(...)` after making any scope changes and
        determining their children.

        Args:
            scope (dict, optional): Variable scope. Defaults to global scope.
                Used recursively to pass information along the tree.
            children (List[Node], optional): List of children. Defaults to [].
                Most subclasses will not include this arg in their generate
                signature since they define their own children.
            traversal_order (List[Node], optional): List of nodes in the
                order of traversal by render_and_execute, render, and execute.
                Use `None` to indicate `self`. Defaults to post-order traversal.
                Most subclasses will not include this arg in their generate
                signature since they define their own children.
            **kwargs: Additional keyword arguments (if applicable). Recursively passed
                along to children.

        Returns:
            Optional[Dict]: Updates to the scope of downstream nodes, if any.
        """

        # this should only happen at the top level node
        if scope is None:
            scope = Node.global_scope

        # assign attributes (probabbly supplied by subclass)
        self.children = children
        self.traversal_order = \
            [self if n is None else n for n in traversal_order] \
            if traversal_order is not None \
            else children + [self]  # post-order default

        # make updates before saving self.scope
        # so they get passed on to siblings and parents
        for node in self.traversal_order:
            if node is self:
                self.scope = scope.copy()  # copy the scope so later dict updates don't affect it
            else:
                updates = node.generate(scope=node.scope) or {}
                scope.update(updates)

        # Return scope. Since scope is a dict, self.scope won't
        # be changed when downstream changes are made to it
        # (unless we're talking about objects in the dict)
        return scope

    def render_and_execute(self, env, updates: dict = {}, **kwargs) -> Optional[Dict]:
        """Renders and executes the node recursively and possibly makes updates
        to the scope which are passed on to downstream siblings and parents.

        NOTE: This is a recursive method. It is intended to be called from
        the base of the tree. If just want to render and execute this single
        node, use `render` and `_execute` instead. (However, most nodes with children
        cannot render unless their children have first rendered.)

        Args:
            env: Environment to execute on.
            updates (dict, optional): Updates to the scope of downstream nodes.
                Defaults to {}.
            **kwargs: Additional keyword arguments to pass to exec_func
                (if applicable) and/or children.

        Returns:
            Optional[Dict]: Updates to the scope of downstream nodes, if any.
        """
        cumulative_updates = updates
        for node in self.traversal_order:
            node.scope.update(cumulative_updates)
            if node is self:
                self.render()
                new_updates = self._execute(env, **kwargs)
            else:
                new_updates = node.render_and_execute(
                    env, updates=cumulative_updates, **kwargs)
            cumulative_updates.update(new_updates or {})
        return cumulative_updates

    def render(self, **kwargs) -> str:
        """Renders the node to a string.
        In most cases, render should be performed using post-order traversal.
        Nodes may use information in their scope to render themselves.

        NOTE: this is a non-recursive method. Individual subclasses however
        may override this method to perform recursive rendering. E.G.: The
        Sentence class renders its children before rendering itself.

        Args:
            **kwargs: Additional keyword arguments (if applicable)

        Returns:
            str: Rendered string.
        """
        raise Exception('Not implemented.')

    def execute(self, env, updates: dict = {}, **kwargs) -> Optional[Dict]:
        """Executes the node and possibly makes updates to the scope
        which are passed on to downstream siblings and parents.

        NOTE: This is a recursive method. It is intended to be called from
        the base of the tree. If just want to execute this single node's
        exec_func, use `_execute` instead.

        Args:
            env: Environment to execute on.
            updates (dict, optional): Updates to the scope of downstream nodes.
                Defaults to {}.
            **kwargs: Additional keyword arguments to pass to exec_func
                (if applicable) and/or children.

        Returns:
            Optional[Dict]: Updates to the scope of downstream nodes, if any.
        """
        cumulative_updates = updates
        for node in self.traversal_order:
            node.scope.update(cumulative_updates)
            if node is self:
                # non-recursive call
                new_updates = self._execute(env, **kwargs)
            else:
                # recursive call
                new_updates = node.execute(
                    env, updates=cumulative_updates, **kwargs)
            cumulative_updates.update(new_updates or {})
        return cumulative_updates

    def _execute(self, env, **kwargs) -> Optional[Dict]:
        """Executes the single node and possibly makes updates to the scope
        which are passed on to downstream siblings and parents.

        Args:
            env: Environment to execute on.
            **kwargs: Additional keyword arguments to pass to exec_func
                (if applicable) and/or children.

        Returns:
            Optional[Dict]: Updates to the scope of downstream nodes, if any.
        """
        if self.exec_func is not None:
            return self.exec_func(env=env, scope=self.scope, **kwargs)
        else:
            return  # many nodes simply supply information but don't do anything

    def matches(self, syntax: Node):
        """Checks if the node matches the syntax.

        Args:
            syntax (Node): syntax to match.

        Returns:
            bool: True if the node matches the syntax.
        """
        if self == syntax:
            return True
        raise Exception('Not implemented.')

    def __repr__(self) -> str:
        return self.render()

    def __str__(self) -> str:
        return self.render()


class StringNode(Node):

    def __init__(self, string: str, exec_func: _can_execute = None) -> None:
        """Initializes a string node.

        Args:
            string (str): String literal.
            exec_func (can_execute, optional): Function that is called when
                the node graph is executed.  Defaults to None. `exec_func`
                allows defining templates using type annotations like so:
                ```python
                @TemplateNode
                def MOUSE_ACTION(env, scope, **kwargs):
                    x, y = scope['x'], scope['y']
                    env.move_mouse(x, y)
        """
        self.string = string
        super().__init__(exec_func=exec_func)

    def render(self) -> str:
        return self.string

    def matches(self, syntax: Node) -> bool:
        return isinstance(syntax, StringNode) and self.string == syntax.string


class EmptyNode(StringNode):

    def __init__(self, exec_func: _can_execute = None) -> None:
        """Initializes an empty node.

        EmptyNode are useful for
        - building optional nodes
        - setting arbitrary scope values
        - making arbitrary execution statements

        Args:
            exec_func (can_execute, optional): Function that is called when
                the node graph is executed.  Defaults to None. `exec_func`
                allows defining templates using type annotations like so:
                ```python
                @TemplateNode
                def MOUSE_ACTION(env, scope, **kwargs):
                    x, y = scope['x'], scope['y']
                    env.move_mouse(x, y)
        """
        super().__init__('', exec_func=exec_func)


class ConcatNode(Node):

    def __init__(self,
                 *items: List[Template],
                 N: int = None,
                 exec_func: _can_execute = None,
                 **named_items: Dict[str, Node]) -> None:
        """Initializes a ConcatNode.

        A ConcatNode is a node that concatenates its children during the render method.

        If supplied, children can be supplied as either positional or keyword arguments
        but not both. If neither are supplied, children must be supplied during the
        generation method. (This is useful for nodes that determine their children at
        generation-time like UnionNode.)

        Under the hood, ConcatNode deep-copies its children. This allows reusing the
        same child node in multiple places in the syntax, since if they were idenical
        objects, they would always have the same generation: It would quickly become
        unrealistic if the subject and object were always the same in "<NP> <V> <NP>".

        Args:
            *items (List[Template]): List of items. Optional if supplying named items.
            N (int, optional): Number of items to choose from. Defaults to None (all items).
            exec_func (can_execute, optional): Function that is called when
                the node graph is executed.  Defaults to None. `exec_func`
            **named_items (Dict[str, Node]): Children with named keys.
        """
        assert not (named_items and items), \
            "Cannot provide both named and positional children"

        # init with dict as positional arg; E.G.: ConcatNode({"a"=A, "b"=B, "c"=C})
        if len(items) == 1 and isinstance(items[0], dict):
            named_items = items[0]
        # init with positional arg spread; E.G.: ConcatNode(A, B, C)
        if items:
            all_children = map(Node.__new__, items)
        # init with keyword arg spread; E.G.: ConcatNode(a=A, b=B, c=C)
        elif named_items:
            all_children = named_items.values()
            all_children = map(Node.__new__, all_children)
            for name, child in zip(named_items.keys(), all_children):
                child.scope_key = name
        # init with no args; E.G.: ConcatNode()
        else:
            all_children = []
        self._all_children = map(deepcopy, all_children)

        if N is not None:
            self.N = N
            children_it = itertools.combinations(self._all_children, N)
            children_it = list(children_it)
            random.shuffle(children_it)
            self.children_it = iter(children_it)

        super().__init__(exec_func=exec_func)

    def generate(self,
                 scope: dict = None,
                 children: List[Node] = [],
                 traversal_order: List[Node] = None,
                 **kwargs) -> Optional[dict]:

        # if children are supplied now, update the all_children list
        if len(children) > 0:
            self._all_children = map(deepcopy, children)

        # maybe perform random sampling
        if self.N:
            assert self.N > 0, "N must be greater than 0"
            assert len(self._all_children) > self.N, \
                "N must be less than the number of children"
            children = next(self.children_it)
        else:
            children = self._all_children

        # generate children
        return super().generate(scope=scope, children=children,
                                traversal_order=traversal_order, **kwargs)

    def render(self) -> str:
        return ''.join(map(lambda c: c.render(), self.children))

    def matches(self, syntax: Node):
        """Checks if the node matches the syntax.

        Args:
            syntax (Node): syntax to match.

        Returns:
            bool: True if the node matches the syntax.
        """
        # early exits
        if self == syntax:
            return True
        if not isinstance(syntax, ConcatNode):
            return False

        # compare children
        if syntax.N is not None:
            if len(self.children) != syntax.N:
                return False
            # we have to test all possible branches here
            # this means we need to generate all possible N-tuples of cst._all_children
            # with order preserved
            all_possible_children = itertools.combinations(
                syntax._all_children, syntax.N)
            all_possible_children = list(all_possible_children)
            random.shuffle(all_possible_children)
        else:
            if len(self.children) != len(syntax._all_children):
                return False
            all_possible_children = [syntax._all_children]
        return any(
            all(is_legal(a, b)
                for a, b in zip(self.children, possible_children))
            for possible_children in all_possible_children
        )


class RepeatNode(ConcatNode):

    def __init__(self,
                 item: Template,
                 sep: Template = None,
                 last_sep: Template = None,
                 *,
                 N: int = None,
                 repititions: int = None,
                 exp_lambda: float = 0.333,
                 min_count: int = 0,
                 max_count: int = None,
                 exec_func: _can_execute = None) -> None:
        """Initializes a RepeatNode.

        A RepeatNode is a node that makes 1 or more repitions of a `item` separated by
        `sep` (if given) and the last item separated by `last_sep` (if given). If
        `repititions` is given, then the item is repeated exactly repititions times.
        Otherwise, `repititions` is sampled from an Exponential distribution parametrized
        by `exp_lambda` and bound within [min_count, max_count].

        The mean (average) of the exponential distribution is 1 / exp_lambda.

        Note that repitition occurs at generation time, so unless supplied as `LazyTemplate`s,
        repeated nodes will be identical underlying objects.

        Under the hood, RepeatNode is a ConcatNode with no children. During generation
        it generates its children and forwards them to the generation method of ConcatNode.

        Args:
            item (Template): Item to repeat.
            sep (Template, optional): Separator between items. Defaults to None.
            last_sep (Template, optional): Separator between last and second to last items.
                Defaults to None.
            N (int, optional): Number of items to choose from. Defaults to None (all items).
            repititions (int, optional): Number of repetitions. Defaults to None. If
                specified, then poison parameters, min_count, and max_count are ignored.
            exp_lambda (float, optional): Lambda for Exponential distribution. Defaults to 1.0.
                Lower values mean more frequent repetitions. Ignored if N is given.
            min_count (int, optional): Minimum number of repetitions. Defaults to 0.
            max_count (int, optional): Maximum number of repetitions. Defaults to None.
            exec_func (can_execute, optional): Function that is called when the node graph
                is executed.  Defaults to None.
        """
        self.item = item
        self.sep = sep
        self.last_sep = last_sep
        self.repititions = repititions
        self.exp_lambda = exp_lambda
        self.min_count = min_count
        self.max_count = max_count
        super().__init__([], N=N, exec_func=exec_func)

    def generate(self, scope: dict = None, **kwargs) -> Optional[dict]:

        if self.repititions is None:
            self.repititions = int(self.random.expovariate(self.exp_lambda))
            self.repititions = max(self.repititions, self.min_count)
            if self.max_count is not None:
                self.repititions = min(self.repititions, self.max_count)

        items = []
        for i in range(self.repititions):
            items.append(items[i])
            if i < self.repititions - 2 and self.sep is not None:
                items.append(self.sep)
            elif i == self.repititions - 2:
                if self.last_sep is not None:
                    items.append(self.last_sep)
                elif self.sep is not None:
                    items.append(self.sep)

        return super().generate(scope=scope, children=items, **kwargs)


class UnionNode(ConcatNode):

    def __init__(self, *items: List[Template], **named_items: Dict[str, Node]) -> None:
        """Initializes a UnionNode.

        A UnionNode is a node that chooses one of its children in the render method.
        Note that the choice happens at generation time, so the render is deterministic.

        Under the hood, UnionNode is ConcatNode with N=1 (i.e.: only 1 item selected).

        Args:
            *items (List[Template]): List of items. Optional if supplying named items.
            **named_items (Dict[str, Node]): Children with named keys.
        """
        super().__init__(*items, N=1, **named_items)


class OptionalNode(UnionNode):

    def __init__(self, item: Template) -> None:
        """Initializes a OptionalNode.

        A OptionalNode is a node that represents the union of a given node and an empty node.
        Note that the choice happens at generation time, so the render is deterministic.

        Under the hood, OptionalNode is a UnionNode between an EmptyNode or the item.

        Args:
            item (Template): Item to repeat.
        """
        super().__init__(item, EmptyNode())


class ExcludeNode(Node):

    def __init__(self, lhs, rhs, depth: int = None) -> None:
        """Initializes an ExcludeNode.

        An ExcludeNode is a node that forces its LHS to re-generate if it matches the RHS.

        NOTE: This algorithm is has a high complexity

        NOTE: It is assumed that at least one generation of the LHS does not match the RHS.
        This algorithm is not guaranteed to terminate otherwise.
        """
        self.lhs = lhs
        self.rhs = rhs
        self.depth = depth
        super().__init__()

    def generate(self, scope: dict = None, **kwargs) -> Optional[dict]:
        try:
            while True:
                new_scope = super().generate(
                    scope=scope, children=[self.lhs], **kwargs)
                if not ast.matches(self.rhs):
                    return new_scope
        except RecursionError:
            if self.depth is None:
                raise
            if self.depth > 0:
                self.depth -= 1
                return self.generate(scope=scope, **kwargs)
            raise
        except StopIteration:
            raise ValueError(
                "No more generations possible and/or None are legal values")


def is_legal(ast: Node, cst: Node) -> bool:
    """Recursively checks if an abstract syntax tree `ast` (the generated node)
    matches any possible generations of the concrete syntax tree `cst` (the grammar)

    Args:
        ast (Node): Abstract syntax tree.
        cst (Node): Concrete syntax tree.

    Returns:
        bool: True if the AST matches the CST.
    """
    # testing type in reverse order of their definition since going from
    # Node to ConcatNode to ... would always default to the Node case

    if isinstance(ast, ConcatNode):
        if isinstance(cst, ConcatNode):
            return ast.matches(cst)
        else:
            return False
    elif isinstance(ast, RepeatNode):
        if isinstance(cst, RepeatNode):
            return is_legal(ast.item, cst.item) and is_legal(ast.sep, cst.sep) and is_legal(ast.last_sep, cst.last_sep)
        else:
            return False
    elif isinstance(ast, UnionNode):
        if isinstance(cst, UnionNode):
            return all(is_legal(a, b) for a, b in zip(ast.children, cst.children))
        else:
            return False
    elif isinstance(ast, OptionalNode):
        if isinstance(cst, OptionalNode):
            return is_legal(ast.item, cst.item)
        else:
            return False
    elif isinstance(ast, ExcludeNode):
        if isinstance(cst, ExcludeNode):
            return is_legal(ast.lhs, cst.lhs) and is_legal(ast.rhs, cst.rhs)
        else:
            return False
    elif isinstance(ast, EmptyNode):
        return isinstance(cst, EmptyNode)
    elif isinstance(ast, LiteralNode):
        return isinstance(cst, LiteralNode) and ast.value == cst.value
    elif isinstance(ast, VariableNode):
        return isinstance(cst, VariableNode) and ast.name == cst.name
    elif isinstance(ast, FunctionNode):
        return isinstance(cst, FunctionNode) and ast.name == cst.name
    elif isinstance(

# convenience types
N=Node
S=StringNode
E=EmptyNode
C=ConcatNode
R=RepeatNode
U=UnionNode
O=OptionalNode


# this is what an example syntax definition should look like:
DOWN=U("down", "press")
UP={"up", "release"}

BUTTON_VB=U("click", DOWN, UP)
BUTTON_SIDE={"left", "right", "middle"}

BUTTON_ACTION={
    (BUTTON_VB, "the", BUTTON_SIDE, "button"),
    ([BUTTON_SIDE], BUTTON_VB)
}

ACTION={
    {"mouse": BUTTON_ACTION},
    {"keyboard": 'press A'},
}

TASK=R(ACTION, sep=", ", last_sep=" and ", exp_lambda=0.1)

"""TODO: refactor much of init logic into separate generate() function

# 1. define syntax
# 2. generate templates
# 3. render and execute templates

tasks = []
for i in range(10):
    task = TASK.generate(scope=Box(), **kwargs)
    # scope is saved on each node, so we just make an anonymous one
    # **kwargs for dev-level customization (like passing a param to a deep node)
    tasks.append(task)

for task in tasks:
    print(task.render())
    task.execute(env=env)

'''
"""
