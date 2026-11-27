/// Route paths. Every screen is reachable by a path (deep links, notifications, search hits).
abstract final class Routes {
  static const splash = '/splash';
  static const signIn = '/sign-in';
  static const connect = '/connect';
  static const server = '/server';

  // Tab branches (floating tab bar): Chats · Market · Me, plus the Attention circle.
  static const chats = '/chats';
  static const market = '/market';
  static const me = '/me';
  static const attention = '/attention';

  static String thread(String id, {int? around}) =>
      around == null ? '$chats/thread/$id' : '$chats/thread/$id?around=$around';
  static const archived = '$chats/archived';
  static const search = '/search';

  static const agents = '/agents';
  static String agent(String id) => '/agent/$id';
  static String agentSettings(String id) => '/agent/$id/settings';
  static String agentMemory(String id) => '/agent/$id/memory';
  static String agentSkills(String id) => '/agent/$id/skills';
  static String routines({String? agentId}) =>
      agentId == null ? '/routines' : '/routines?agent=$agentId';
  static String newGroup({List<String> members = const []}) => members.isEmpty
      ? '/groups/new'
      : '/groups/new?members=${members.join(',')}';
  static String groupSettings(String id) => '/groups/$id/settings';

  static String artifacts({String? threadId, String? agentId}) {
    final q = {'thread': ?threadId, 'agent': ?agentId};
    return q.isEmpty
        ? '/files'
        : Uri(path: '/files', queryParameters: q).toString();
  }

  static String artifact(String id) => '/files/$id';
  static String image(String id) => '/files/$id/image';
  static String charts({String? threadId, String? agentId, String? chartId}) {
    final q = {'thread': ?threadId, 'agent': ?agentId, 'chart': ?chartId};
    return q.isEmpty
        ? '/charts'
        : Uri(path: '/charts', queryParameters: q).toString();
  }

  static const tasks = '/tasks';
  static const ownerKnowledge = '/me/knowledge';
  static const account = '/settings/account';
  static const integrations = '/settings/integrations';
  static const models = '/settings/models';
  static const notifications = '/settings/notifications';
  static const voice = '/settings/voice';
  static const running = '/settings/running';
  static const appearance = '/settings/appearance';
  static const usage = '/settings/usage';
  static const about = '/settings/about';
}
