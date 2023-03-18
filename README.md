# node-tree

`node-tree` is a module for programming with trees. It provides a set of tools for generating synthetic demonstration-description pairs using psuedo context-free grammar (you can extend the generation phase of any node so you're not confined to CFG's), rendering them into complex natural language templates, and then executing them. The basic use is:

0. `pip install node-tree`
1. define your grammar
2. start the tree (this calls generate, render, and execute in-order recursively)

## Example

```python
from artificial_grammar_toolkit import *

# We will generate labeled demos for this environment:
Point = tuple[int, int]
class Env:
    players: list[str, Point]
    def move(self, player: str, direction: str): ...
env = Env([('Tom', (2,3)), ('Sally', (4,1))])

# define grammar

# this node renders to "Tom", "Jerry", "Barry", or "Sally"
SUBJECT = U([name for name, _ in env.players])
# this node renders to "up", "down", "left", or "right"
DIRECTION = U(['up', 'down', 'left', 'right'])

# the MOVE node renders to "moves", "walks", "jumps", or "runs" 
@U('moves', 'walks', 'jumps', 'runs')
def MOVE(env, scope):
  env.move(scope['SUBJECT'], scope['DIRECTION'])

# you could add other verbs in the vocabulary here
VERB = U(MOVE) 
# this node renders to "N", "N who V", or "N V"
@U(SUBJECT, (SUBJECT, 'who', VERB))
def NOUN_PHRASE(env, scope):
  ...
# this is a simple sentence. Let's see what it generates...
SENTENCE = T(R(NOUN_PHRASE, VERB, DIRECTION, sep=(',', {'and', 'but'}))) 

# generate a task tree
tree = SV_SENTENCE.generate() # now the tree represents a random sentence like "Tom walks up"

# render and execute
# Given the tree, this will call env.move('Tom', 'up') and give us an English description: "Tom walks up"
tree.render_and_execute(env=env)

# TODO: connect your data pipeline here
```

## Nodes

```text
Node
: LiteralNode
  : EmptyNode
: ConcatNode
  : RepeatNode
    : WhileNode
      : DoWhileNode
    : ForNode
  : UnionNode
    : OptionalNode
: ExcludeNode
: SwitchNode, 
  : IfNode, IfElseNode
```

## Concepts

Define your concrete syntax with:

- Python subclasses: subclass Node, override execute, render, etc.
- decorators @Node, @node.execute, @node.render, @node.whatever: If any of the functions recieve only a function, then a new method is created with that name. This behavior is caused by overriding the dot lookup method on the Node class.
- external CFG text files: Uses Python ast library to convert grammar to Node's which can then be decorated with actions. Supports:
  - `"<terminals>"`: string in single or double quotes
  - `<VARIABLES>`: any valid Python variable name
  - union operator `<lhs>|<rhs>`: generates either the lhs or rhs
  - star operator `<lhs>*`: generates zero or more of the lhs
  - plus operator `<lhs>+`: generates one or more of the lhs
  - optional operator `<lhs>?`: generates zero or one of the lhs
  - grouping `(...)`: parentheses
  - concatenation operator `<lhs>&<rhs>` or `<lhs> <rhs>`: generates the lhs and the rhs
- Templates: Shorthand for defining syntax. Can be a nested structure of any of the following:
  - `node: Node`: A single node.
  - `string: str`: a lot of possibilities:
    - If the string can be interpreted as a context-free grammar, then the start symbol of that grammar
    - If the string evaluates to a `Template`, then that object
      Otherwise, a StringNode with the string value.
  - `fn: LazyTemplateFn`: lazy template generation. kwargs are inherited from the parent Node. Useful for recursive grammars.
  - `Set[Node]`: Converted to UnionNode of set content.
  - `Tuple[Union[[Node],int]]`: Converted to a ConcatNode with children taken from the tuple content. 0 or 1 of the lists items may be an int. If 1 int is given, then that int is used for the `N` keyword argument of the ConcatNode constructor. See `ConcatNode.__init__` docstring for more details.
  - `Dict[str, Any]`: Converted to a ConcatNode using kwargs from dict. Useful for supplying in custom kwargs. See ConcatNode __init__ docstring for more details.
  - `List[Union[[Node],int]]`: optional value, optional concatenation, or empty.
    - If the list contains exactly one node, then it is converted to an OptionalNode with the node as its child.
    - If the list contains more than one node, then it is converted to an OptionalNode with a ConcatNode as its child. The list contents are used to initialize the ConcatNode. See the Tuple case above for more details.
    - If the list is empty, then an EmptyNode is returned.
  - `Iter[Node] (|*nodes: List[Node]|)`: Lazy concatenation of nodes. Values inside banana brackets (only supported in the coconut language) are not evaluated until the node is initialized. This allows defining recursive grammars. Converted to a ConcatNode on initialization.

Additionally, compose syntax with Python operators:

- `LHS + RHS` or `LHS & RHS` or `LHS and RHS`: ConcatNode
- `LHS | RHS` or `LHS or RHS`: UnionNode
- `LHS * repeats: int`: RepeatNode with `repeats` as the `N` keyword argument.
- `+LHS`: RepeatNode with lower_bound = 1
- `generator - discriminator`: ExcludeNode

Nodes also support:

- `contains`: for testing child node membership
- index access: for accessing child nodes
- `len`: for getting the number of child nodes
- `iter`: for iterating over child nodes
- `repr`: for getting a string representation of the node. Defaults to `self.render`
- `str`: for getting a string representation of the node. Defaults to `self.render`

Nodes work in __passes__: By default, `Node.passes = [self.generate, self.render, self.execute]`. However this behavior can be altered by changing the methods on a single `node.passes` or a `Subclass.passes`. While the render and execute methods are a convention established by the Node class, you don't have to implement them if you're using a different sequence of passes.

Run the stages recursively in order by calling `root.start()`:

```python
root.start(self,
           rel2: dict[str, any]=None,
           rel3: set[tuple[any, str, any]],
           max_generation_passes=None, # limit infinite generation
           max_passes=None,
           exclude_passes=[], # e.g.: don't execute
           only_passes=None,  # e.g.: first only generate, then only render
           delta_depth_limit=None, # maybe you want to slowly expand the tree
           delta_node_limit=None,  # maybe you want to slowly add nodes
           *args, **kwargs)  # passed on to all stage methods (eg: `env` for execute or `language` for render) -> ...:
    # this function uses self.stages to determine which stages to run
    # it runs each .start recursively before moving on to the next
    # this means that execution and rendering happen just in time
```

There's just a single `.start()` method that runs generation, execution, and rendering. Thus, unless `exclude_passes` are specified, generation time == execution time == rendering time. This means a `RepeatNode` could determine whether to repeat an action (add another generation pass) based on the result of the execution. However, nodes should have a failsafe in case execution or rendering is excluded.

By default, generation, render, and execution takes place in post-order traversal. However there are corner cases where this is not desireable. Consider a `"<SIMPLE_CLAUSE> = <SUBJECT> <VERB> <OBJECT>"` grammar. During the execution pass, VERB needs knowledge of both SUBJECT *and OBJECT* to determine the appropriate action. For this reason, SIMPLE_CLAUSE modifies its traversal to traverse VERB last.

All nodes have a `.rendering` attribute. (LiteralNodes are a convenience type.) This is written whenever the node renders. ConcatNode's have a `.reduce` method defaults to the `+` operator. To retrieve the final rendering of the sentence, just grab the `.rendering` attribute of the root node. Every sub-parent in the tree also has a `.rendering` attribute of their phrase or sentence or whatever.

Nodes pass information around using a `rel2` dict and `rel3` set in the order of traversal. The `rel2` dict is a dictionary of key-value pairs, which are useful for pronoun resolution and other things. When the generation pass runs on `Node`, it adds an entry for each of its children in `rel2` for each of their scope_keys. By default, a Node's scope_keys only include the name of its type (`[str(Self)]`) -- which is useful for remembering the most recent subject (since only one "subject" key can exist in `rel2` at any given time) -- but subclasses and instances also have the ability to change their scope_keys. As a special case, the dictionary initialization template syntax case creates a ConcatNode with additional scope keys added corresponding to the dictionary keys associated with each child. The `rel3` set is a set of entity relations, which are useful for testing whether a node represents a subtype of another node (like is SUBJECT a COMPUTER?).

The control flow nodes (like `IfNode`) are initialized with a `condition` attribute. This is a function that returns a boolean. The `condition` function is called with the current node, `rel2` dict, and `rel3` set as arguments. You can use these convenience methods for making your conditions:

- `children(x)`: returns a list of direct children of x
- `descendants(x, depth_limit=None)`: returns a list of all descendants of x
- `leaves(x)`: returns a list of all leaves (last children) of x
- `parent(x)`: returns the parent of x
- `ancestors(x, height_limit=None)`: returns a list of all ancestors (parent, grandparent, ..., root) of x
- `root(x)`: returns the root ancestor of x
- `siblings(x, side='left'|'right'|'all')`: returns a list of all siblings of x
- `left_siblings(x)`: returns a list of all left siblings of x
- `right_siblings(x)`: returns a list of all right siblings of x
- `sibling(x, side='left'|'right')`: returns the sibling of x
- `left_sibling(x)`: returns the left sibling of x
- `right_sibling(x)`: returns the right sibling of x
- `cousins(x, common_generation=2, side='left'|'right'|'all')`: returns a list of all cousins of x
- `left_cousins(x, common_generation=2)`: returns a list of all left cousins of x
- `right_cousins(x, common_generation=2)`: returns a list of all right cousins of x
- `family(x, common_generation=None, side='left'|'right'|'all')`: returns a list of all family (parent, siblings, cousins, self) of x
- `left_family(x, common_generation=None)`: returns a list of all left family of x
- `right_family(x, common_generation=None)`: returns a list of all right family of x
- `nuclear_family(x, include_self=True)` or `immediate_family`: returns a list with the parent, siblings, and x
- `siblings_and_cousins(x, common_generation=2, side='left'|'right'|'all')`: returns a list of all siblings, 1st-cousins, 2nd-cousins, etc. (family tree without parent) of x
- `left_siblings_and_cousins(x, common_generation=2)`: returns a list of all left siblings, 1st-cousins, 2nd-cousins, etc. (family tree without parent) of x
- `right_siblings_and_cousins(x, common_generation=2)`: returns a list of all right siblings, 1st-cousins, 2nd-cousins, etc. (family tree without parent) of x

If a node has nondeterministic generation (like action selection), it is desirable to program this using iterators over all possibilities. The reason is that ExcludeNodes work by repeatedly regenerating the generator node until is doesn't match the condition. (There is a convenience argument on `ExcludeNode.__init__` to pass in a Node for the exclude condition. This Node is converted into a depth-first recursive `match` function if possible or a shuffled generator of all possible renderings. The `match` function recieves all the kwargs of the ExcludeNode which include: exclude_depth_limit=3, strikeout_testing=False, allowed_strikes=0, score_testing=True, allowed_penalty=0.0. This function also merge hierarchies of UnionNodes into a single UnionNode since `or` is associative) The exclude_node.generate method also takes in `default_node=E()` argument which makes an empty string if a non-excluded tree could not be generated and `exclude_test_limit=None` to mitigate problems with non-halting generators (like random sampling).

## Extensions

NodeCrawler is a

You can use THIS REPO with the `ExpandNodeCrawler(replace=True, insert=False, change_order=False)` which uses `deeppy.expand(node.children, node=node, locals=locals(), ...)` to recursively possibly add nodes.

## Popular Use-Cases

Generic:

- Pairs node execution and string rendering
- Lots of natural language primitives
- Convenience extensions to gym.Env for data collection

Synthesize relational data for training natural language models:

Recipes (Generic)

- No execution, just rendering
- Proof of concept for synthetic data generation
- With NDSDM (below), can be used to instruct humans to cook

Programming (Generic)

- Realtime execution supported if an REPL exists
- Notebook execution supported if a kernel exists
- Render in code (Python, JavaScript, HTML, CSS, Java, C++, C#, C, etc.) or natural language
- variable scope included in rel2
- Only a few primitives (like if, class, list, file, project) are implemented
- Consumers can define more node types and syntax elements

Computer interaction (Generic)

- The computer is the environment. Adds computer action primitives
- FIND_PIXEL(E) node finds location of colored location markers
- GOAL_STATIC(...) node identifies goal states using vision-language model comparison against expected description or image-image embedding similarity

UI (Programming, Computer Interaction):

- Adds nodes for common UI elements in major frameworks (html, mui, android, .NET)
- Executes to generate description-image pairs
- It subclasses Computer Interaction, so provides controlled way to generate demos of particular UI interactions

Blender (Programming)

- Python REPL with bpy imported
- generates description of scene, commands used to get there, and render
- Adds CompositionalNode for working with scene at an abstract level
- Adds VidSeqNode, SceneNode, and other blender-specific nodes
- Adds AddImage node for importing Unsplash, Google Images, etc., Dalle-mini, Blender, or file to generate images from text
- useful for generating 2D and 3D images and animations

Creative (Blender)

- Adds FictionNode, NonfictionNode, StoryNode, ChapterNode, SectionNode, ParagraphNode, RhymeNode and modifies the generic language nodes to support writing several types of literature
- Adds nodes for common music primitives and imports MIDI synthesizers
- Adds STTNode for speech generation
- Uses blender's ImageNode and SceneNode to generate accompanying images or animations (2d or 3d)
- Useful for { songs, audiobooks, books, movies, picture book, powerpoint, etc. } x { education, entertainment }

Website (UI, Creative):

- Makes { news, wiki, project, business, entertainment } sites

## Generic Use-Cases

- node-tree for demo-description pair synthesis.
  - Useful for imitation learning and training generative models
  - The task description is attached to the root when done
  - Description can be parametrized by detail

- constrained node-tree for generating possible options:
  - initial task attached to root; this constrains what may be generated
  - iterative generate, render, confirm, rollback until task is confirmed
  - execute and render to generate description-demo pairs
  - like NDSDM but w/o a policy. Useful for understanding how the policy recieves options which is useful to mitigating safety issues

- node-tree + deeppy for structured decision making (NDSDM):
  - this has been moved to tensorcode
  - passes: [generate, policy, render, execute]
  - initial task attached to root
  - tree is a GNN network
  - when the policy pass reaches a TASK node,
    - the policy reads the entire tree including task description on root and environment state
    - the policy might decide to add/insert children to the tree using `deeppy.extend_list`
  - render pass updates task description on the root and asks for user confirmation
  - if user confirms, execute pass executes the tree
  - otherwise,
    - maybe backtrack most recent policy pass
    - maybe backtrack most recent generation pass
    - run (generate and) policy passes again
  - once a subtree is executed, it is marked to be ignored in future runs, but it remains on its parent for reference
  - the tree can be saved if enterprises want precise macros to run

## Example: Generating Computer Interaction Demonstration-Description Pairs

### Syntax Definitions

```cfg
E = ""
S = " "
HYPHEN = S | -
CMD_TERMINATOR = E|,|.|!
AND = "and"|"&"
OR = "or"|"|"

PARALLEL_ADV = at the same time | simultaneously
INTENSITY_ADV = more | less | not as much
SPEED_ADV = quickly | slowly
CAUTION_ADV = carefully | with caution
MOVEMENT_ADV = CAUTION_ADV | SPEED_ADV | INTENSITY_ADV
ADV = PARALLEL_ADV | INTENSITY_ADV | SPEED_ADV | MISC_ADV

SPEED_VB = faster | slower | quick

REG_KEY := all non-modifier keys
MOD_KEY := all modifier keys
KEY := REG_KEY | MOD_KEY
KEY_COMBO_NO_SEP := MOD_KEY? KEY_COMBO_NO_SEP KEY? | E
KEY_COMBO_PLUS := MOD_KEY + KEY_COMBO_PLUS | KEY_COMBO_PLUS + KEY | KEY | E
KEY_COMBO_AND_PARTIAL := MOD_KEY AND KEY_COMBO_AND_PARTIAL | KEY_COMBO_AND_PARTIAL AND KEY | KEY | E
KEY_COMBO_AND := KEY_COMBO_AND_PARTIAL PARALLEL_PREPOSITION?
KEY_COMBO := KEY_COMBO_NO_SEP | KEY_COMBO_PLUS | KEY_COMBO_AND
KEY_ACTION := press | release

BUTTON_SIDE := left | right | middle
BUTTON_NAME := BUTTON_SIDE (mouse?) button
BUTTON_ABBREV := LMB | RMB | MMB
BUTTON_ACTION := press|release|click|double click|triple click

SCROLL_DIR := up|down

CARDINAL_POS := top | bottom | left side | right side
CARDINAL_DIR := (up | down | left | right)(E | ward | wards)
TEXT_POS := start | beginning | middle | halfway(HYPHEN)point | end
TEXT_DIR := (forward | backward)(s?)
DIR := CARDINAL_DIR | TEXT_DIR

### Motor-level tasks

Examples: LMB down, press A, backspace

MOTOR_ACTION :=
  // keyboard
  KEY_ACTION |
  KEY_COMBO |
  SPEED_ADV? KEY_ACTION KEY_COMBO |
  KEY_ACTION KEY_COMBO SPEED_ADV? |
  SPEED_ADV? KEY_ACTION the KEY_COMBO key(s?) |
  KEY_ACTION the KEY_COMBO key(s?) SPEED_ADV? |
  SPEED_ADV? KEY_ACTION key(s?) KEY_COMBO |
  KEY_ACTION key(s?) KEY_COMBO SPEED_ADV? |
  // mouse buttons
  BUTTON_ACTION SPEED_ADV? |
  SPEED_ADV? BUTTON_ACTION |
  BUTTON_SIDE |
  BUTTON_NAME |
  BUTTON_ABBREV |
  SPEED_ADV? BUTTON_ACTION the (BUTTON_NAME|BUTTON_ABBREV) |
  BUTTON_ACTION the (BUTTON_NAME|BUTTON_ABBREV) SPEED_ADV? |
  (BUTTON_SIDE | BUTTON_NAME | BUTTON_ABBREV) BUTTON_ACTION |
  // scroll wheel
  SPEED_ADV? scroll SCROLL_DIR? |
  scroll SCROLL_DIR? SPEED_ADV? |
  // mouse movement
  DIR |
  move (the mouse)? DIR MOVEMENT_ADV? |
  MOVEMENT_ADV? move (the mouse)? DIR  |
  (move (the mouse)?)? DIR |
  E
```

### Low-level tasks

Examples: type "hello", click the blue triangle, delete that word

- pages of just different buttons that can be identified by text, color, shape, or image.

### UI understanding

Examples: check the checkbox, scroll the scrollbar, open a window

- traditional forms (input fields and a submit)

### App understanding

Examples: open email, go to "google.com", copy the files in /tmp to /home/jacob/backup

### Language skills

Examples: email Phil that I'll be out tomorrow

### Visual skills

Examples: less general than the others; draw a picture of a dog

### Instruction following

Examples: follow along to the YouTube tutorial, follow these steps to instal tensorflow

## GUI Bot

The most recently specified key / button / direction / action / etc. is usually assumed if one of the variables are missing. Exceptions are "Press A. Press B. Press C. Press. Press. Press" where D, E, and F are implicit, but the bot cannot do this.

Actions are executed by a bot that keeps track of:

- key
- key action
- mouse button
- mouse button action
- scroll direction
- mouse direction
- intensity
- speed
- caution

VP :=
  SPEED_VB |
  MOTOR_ACTION

## Post-processing

1. Random spelling correction
2. Random synonym replacement (use LM to make sure semantic meaning stays similar)
3. Translation to randomly selected language (often based on OS)
4. Random misspellings (I'm not sure if this is a good idea)
